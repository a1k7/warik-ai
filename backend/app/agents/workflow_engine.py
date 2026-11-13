"""Workflow engine with failure isolation, approvals, rejection and bounded retries."""

from __future__ import annotations

import hashlib
import inspect

import json

import logging

import re

from copy import deepcopy

from datetime import datetime, timedelta, timezone

from typing import Optional

from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session, object_session

from app.models import User, Workflow, Goal

from app.models.action_log import ActionLog

from app.schemas.workflow import WorkflowPlan

from app.tools.base import BaseTool, ToolContext, ToolResult

from app.tools.registry import registry
from app.tools.provider_selector import ProviderSelector

logger = logging.getLogger(__name__)

# Long-running tools may legitimately remain active. Only recover an EXECUTING

# checkpoint after this lease expires; uncertain side effects are never replayed.

EXECUTION_LEASE_SECONDS = 15 * 60

TERMINAL_STATES = {

    "COMPLETED", "FAILED", "SKIPPED", "BLOCKED", "CANCELLED", "REJECTED",

    "RECONCILIATION_REQUIRED"

}

def _now_iso() -> str:

    return datetime.now(timezone.utc).isoformat()

def _is_aggregation_tool(step: dict) -> bool:

    tool_name = str(step.get("tool", "")).lower()

    desc = str(step.get("description", "")).lower()

    return (

        "compile" in tool_name or "summary" in tool_name

        or "compile" in desc or "summary" in desc

    )

class WorkflowEngine:

    def __init__(self, db: Session, user: User, tool_registry=None):

       self.db = db

       self.user = user

       self.registry = tool_registry or registry

       self.provider_selector = ProviderSelector(self.registry)

    def _select_step_provider(self, step: dict, tool):
        """Resolve and validate a provider for a provider-backed tool."""
        adapters = getattr(tool, "provider_adapters", ()) or ()
        if not adapters:
            return None, None

        operations = tuple(
            getattr(tool, "supported_operations", ("execute",)) or ()
        )
        operation = step.get("provider_operation")
        if not operation:
            if len(operations) != 1:
                raise ValueError(
                    f"Tool '{tool.name}' requires an explicit provider_operation."
                )
            operation = operations[0]

        selection = self.provider_selector.select(
            capability=getattr(tool, "capability", "general"),
            operation=operation,
            region=step.get("provider_region"),
            tool_name=tool.name,
        )
        if not selection.available:
            reasons = "; ".join(
                f"{item.provider_id}: {item.reason}"
                for item in selection.rejected
            )
            raise ValueError(
                f"No eligible provider for '{tool.name}'. {reasons}"
            )

        requested_provider = step.get("provider_id")
        if requested_provider:
            requested_provider = str(requested_provider).strip().lower()
            selected = next(
                (
                    candidate
                    for candidate in selection.candidates
                    if candidate.provider_id.lower() == requested_provider
                    and candidate.tool_name == tool.name.lower()
                ),
                None,
            )
            if selected is None:
                raise ValueError(
                    f"Provider '{requested_provider}' is not eligible for "
                    f"tool '{tool.name}' and operation '{operation}'."
                )
        else:
            selected = selection.selected

        step["provider_id"] = selected.provider_id
        step["provider_operation"] = operation
        step["provider_selection"] = {
            "provider_id": selected.provider_id,
            "display_name": selected.display_name,
            "tool_name": selected.tool_name,
            "capability": selected.capability,
            "operation": operation,
            "region": step.get("provider_region"),
            "execution_status": selected.execution_status,
            "selected_at": _now_iso(),
        }
        return selection, selected

    def create_workflow(self, conversation_id: int, plan: WorkflowPlan) -> Workflow:

        goal = Goal(

            user_id=self.user.id,

            conversation_id=conversation_id,

            title=plan.goal_title,

            description=plan.goal_description,

            status="PLANNED",

            context_json=plan.context,

        )

        self.db.add(goal)

        self.db.flush()

        steps = [step.model_dump(mode="json") for step in plan.steps]

        for step in steps:

            step.setdefault("status", "PENDING")

            step.setdefault("depends_on", [])

            step.setdefault("required", True)

            step.setdefault("retry_count", 0)

            step.setdefault("max_retries", 1)

            step.setdefault("dep_policy", "tolerate_failure" if _is_aggregation_tool(step) else "all_success")

        workflow = Workflow(

            user_id=self.user.id,

            goal_id=goal.id,

            status="PLANNED",

            steps_json=steps,

        )

        self.db.add(workflow)

        self.db.commit()

        self.db.refresh(workflow)

        return workflow




    def _steps(self, workflow: Workflow) -> list[dict]:
        """
    Return a detached copy of workflow steps.

    SQLAlchemy JSON columns do not automatically track nested mutations.
    Deep-copying ensures changes are made independently and can be
    persisted when assigned back through _save().
    """
        return deepcopy(workflow.steps_json or [])


    def _save(self, workflow: Workflow, steps: list[dict]) -> None:
        """
    Persist workflow steps by assigning a fresh JSON-compatible object.
    """
        workflow.steps_json = deepcopy(steps)
        workflow.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


    def _audit(
        self,
        action: str,
        step: dict,
        message: str,
        workflow_id: int | None = None,
    ) -> None:
        """Persist a user-attributed workflow governance event."""
        self.db.add(ActionLog(
            user_id=self.user.id,
            action=action,
            tool_name=step.get("tool"),
            payload={
                "workflow_id": workflow_id,
                "step_id": step.get("id"),
                "status": step.get("status"),
            },
            result_status="success",
            result_message=message[:1000],
        ))

    def _compare_and_swap_steps(
        self,
        workflow: Workflow,
        old_steps: list[dict],
        new_steps: list[dict],
    ) -> bool:
        """Persist a transition only if the stored workflow state is unchanged."""
        if not isinstance(self.db, Session):
            self._save(workflow, new_steps)
            self.db.commit()
            return True

        session = object_session(workflow)
        if session is None:
            return False

        result = session.execute(
            update(Workflow)
            .where(
                Workflow.id == workflow.id,
                Workflow.user_id == self.user.id,
                Workflow.steps_json == old_steps,
            )
            .values(
                steps_json=deepcopy(new_steps),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            .execution_options(synchronize_session=False)
        )

        if result.rowcount != 1:
            session.rollback()
            session.refresh(workflow)
            return False

        session.commit()
        session.refresh(workflow)
        return True

    def _status_map(self, steps: list[dict]) -> dict[str, str]:

        return {step["id"]: step.get("status", "PENDING") for step in steps}

    def _recover_interrupted_steps(self, workflow: Workflow, steps: list[dict]) -> list[str]:

        """Quarantine stale EXECUTING steps instead of replaying uncertain side effects."""

        now = datetime.now(timezone.utc)

        recovered: list[str] = []

        for step in steps:

            if step.get("status") != "EXECUTING":

                continue

            started_raw = step.get("execution_started_at") or step.get("started_at")

            stale = not bool(started_raw)

            if started_raw:

                try:

                    started = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))

                    if started.tzinfo is None:

                        started = started.replace(tzinfo=timezone.utc)

                    stale = (now - started) > timedelta(seconds=EXECUTION_LEASE_SECONDS)

                except (TypeError, ValueError):

                    stale = True

            if not stale:

                continue

            step_id = str(step.get("id", "unknown"))

            step["status"] = "RECONCILIATION_REQUIRED"

            step["error"] = (

                "Execution was interrupted or exceeded its lease. The side effect "

                "may already have occurred; reconcile its outcome before retrying."

            )

            step["reconciliation_required_at"] = now.isoformat()

            step["reconciliation_reason"] = "stale_execution_checkpoint"

            recovered.append(step_id)

            try:

                self.db.add(ActionLog(

                    user_id=self.user.id,

                    action="workflow.execution.interrupted",

                    tool_name=step.get("tool"),

                    payload={

                        "workflow_id": workflow.id,

                        "step_id": step_id,

                        "execution_id": step.get("execution_id"),

                        "reason": "stale_execution_checkpoint",

                    },

                    result_status="warning",

                    result_message=step["error"],

                ))

            except Exception:

                logger.exception("Could not record interrupted workflow step %s", step_id)

        if recovered:

            self._save(workflow, steps)

            self.db.commit()

        return recovered

    def _is_ready(self, step: dict, status_map: dict[str, str]) -> bool:

        return all(status_map.get(dep) in TERMINAL_STATES for dep in step.get("depends_on", []))

    def _should_block(self, step: dict, status_map: dict[str, str]) -> tuple[bool, str]:

        if _is_aggregation_tool(step):

            return False, ""

        if step.get("dep_policy", "all_success") != "all_success":

            return False, ""

        for dep in step.get("depends_on", []):

            if status_map.get(dep) in {

                "FAILED", "BLOCKED", "REJECTED", "CANCELLED", "SKIPPED",

                "RECONCILIATION_REQUIRED",

            }:

                return True, f"dependency '{dep}' did not complete successfully"

        return False, ""

    @staticmethod

    def _read_result_path(value, path: str):

        """Resolve a constrained dot path through JSON-like dict/list data."""

        if not isinstance(path, str) or not re.fullmatch(

            r"[A-Za-z0-9_-]+(?:\.(?:[A-Za-z0-9_-]+|[0-9]+))*", path

        ):

            raise ValueError("result path has an invalid format")

        segments = path.split(".") if isinstance(path, str) else []

        if not segments or any(segment.startswith("__") for segment in segments):

            raise ValueError("result path has an invalid or unsafe segment")

        current = value

        for segment in segments:

            if isinstance(current, dict):

                if segment not in current:

                    raise KeyError(f"result path segment '{segment}' was not found")

                current = current[segment]

            elif isinstance(current, list) and segment.isdigit():

                index = int(segment)

                if index >= len(current):

                    raise IndexError(f"result list index {index} is out of range")

                current = current[index]

            else:

                raise TypeError(f"cannot resolve result path segment '{segment}'")

        return current

    @staticmethod

    def _params_fingerprint(params: dict) -> str:

        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _inject_dependency_results(self, step: dict, steps: list[dict]) -> dict:

        """Resolve explicit input bindings and preserve legacy summary aggregation."""

        params = deepcopy(step.get("params") or {})

        dependencies = set(step.get("depends_on", []))

        steps_by_id = {item.get("id"): item for item in steps}

        for target, binding in (step.get("input_bindings") or {}).items():

            source_id = binding.get("source_step")

            source_path = binding.get("source_path")

            required = bool(binding.get("required", True))

            if source_id not in dependencies:

                raise ValueError(

                    f"Input binding '{target}' references '{source_id}', which is not a declared dependency."

                )

            if target in params:

                raise ValueError(

                    f"Input '{target}' is defined in both params and input_bindings."

                )

            source = steps_by_id.get(source_id)

            if source is None or source.get("status") != "COMPLETED":

                if required:

                    raise ValueError(

                        f"Input binding '{target}' requires successful dependency '{source_id}'."

                    )

                continue

            if binding.get("requires_verified", False):

                verification_status = (source.get("verification") or {}).get("status")

                if verification_status != "VERIFIED":

                    if required:

                        raise ValueError(

                            f"Input binding '{target}' requires verified output from step '{source_id}'."

                        )

                    continue

            try:

                resolved = self._read_result_path(source.get("result") or {}, source_path)

            except (KeyError, IndexError, TypeError, ValueError) as exc:

                if required:

                    raise ValueError(

                        f"Could not resolve input binding '{target}' from step '{source_id}': {exc}"

                    ) from exc

                continue

            if resolved is None and required:

                raise ValueError(f"Input binding '{target}' resolved to an empty value.")

            params[target] = deepcopy(resolved)

        if _is_aggregation_tool(step):

            params["dependency_results"] = {

                item["id"]: {"tool": item.get("tool"), "result": item.get("result")}

                for item in steps

                if item["id"] in dependencies and item.get("status") == "COMPLETED"

            }

            params["dependency_failures"] = {

                item["id"]: {"tool": item.get("tool"), "error": item.get("error"), "status": item.get("status")}

                for item in steps

                if item["id"] in dependencies and item.get("status") in {"FAILED", "BLOCKED", "REJECTED", "SKIPPED", "RECONCILIATION_REQUIRED"}

            }

        return params

    def execute(self, workflow: Workflow, max_steps: int = 20) -> dict:
        steps = self._steps(workflow)
        reconciliation_required_steps = self._recover_interrupted_steps(
            workflow, steps
        )

        executed: list[str] = []
        new_failures: list[dict] = []
        verification_failures: list[dict] = []
        verified_steps: list[str] = []
        unverified_steps: list[str] = []
        awaiting_approval: Optional[dict] = None

        for _ in range(max_steps):
            status_map = self._status_map(steps)
            next_step = None

            for step in steps:
                if step.get("status") not in {"PENDING", "READY", "APPROVED"}:
                    continue
                if not self._is_ready(step, status_map):
                    continue

                blocked, reason = self._should_block(step, status_map)
                if blocked:
                    if step.get("required", True):
                        step["status"] = "BLOCKED"
                        step["error"] = f"Blocked: {reason}"
                    else:
                        step["status"] = "SKIPPED"
                        step["error"] = f"Skipped optional step: {reason}"
                    self._save(workflow, steps)
                    self.db.commit()
                    continue

                next_step = step
                break

            if next_step is None:
                break

            tool = self.registry.get(next_step.get("tool", ""))

            try:
                params = self._inject_dependency_results(next_step, steps)
            except Exception as exc:
                if not next_step.get("required", True):
                    next_step["status"] = "SKIPPED"
                    next_step["error"] = (
                        "Skipped optional step: dependency input resolution "
                        f"was unavailable: {str(exc)[:700]}"
                    )
                else:
                    next_step["status"] = "FAILED"
                    next_step["error"] = (
                        f"Input resolution failed: {str(exc)[:700]}"
                    )
                    new_failures.append(next_step)

                self._save(workflow, steps)
                self.db.commit()
                continue

            validated_params = None
            if tool is not None:
                try:
                    validated_params = tool.input_schema(**params)
                    if hasattr(validated_params, "model_dump"):
                        params = validated_params.model_dump(mode="json")
                except Exception as exc:
                    if next_step.get("input_bindings"):
                        next_step["status"] = "FAILED"
                        next_step["error"] = (
                            "Resolved input validation failed: "
                            f"{str(exc)[:700]}"
                        )
                        new_failures.append(next_step)
                        self._save(workflow, steps)
                        self.db.commit()
                        continue
                    # Legacy/non-bound plans retain dispatch-time validation.
                    validated_params = None

            # Resolve provider before approval so the exact provider is approved.
            selection = None
            selected_provider = None
            if tool is not None and getattr(tool, "provider_adapters", ()):
                try:
                    selection, selected_provider = self._select_step_provider(
                        next_step, tool
                    )
                    self._save(workflow, steps)
                    self.db.commit()
                except Exception as exc:
                    next_step["status"] = "FAILED"
                    next_step["error"] = (
                        f"Provider selection failed: {str(exc)[:700]}"
                    )
                    new_failures.append(next_step)
                    self._save(workflow, steps)
                    self.db.commit()
                    continue

            tool_requires_approval = bool(
                tool
                and (
                    getattr(tool, "requires_confirmation", False)
                    or getattr(tool, "is_mutating", False)
                )
            )
            approval_required = (
                bool(next_step.get("approval_required"))
                or tool_requires_approval
            )

            if approval_required:
                next_step["approval_required"] = True
                fingerprint_payload = params
                if selected_provider is not None:
                    fingerprint_payload = {
                        "params": params,
                        "provider_id": selected_provider.provider_id,
                    }
                fingerprint = self._params_fingerprint(fingerprint_payload)
                approved_fingerprint = next_step.get("approval_fingerprint")

                legacy_static_approval = (
                    next_step.get("status") == "APPROVED"
                    and bool(next_step.get("approval_granted", False))
                    and not approved_fingerprint
                    and not next_step.get("input_bindings")
                    and not next_step.get("depends_on")
                )
                already_approved = (
                    next_step.get("status") == "APPROVED"
                    and bool(next_step.get("approval_granted", False))
                    and (
                        approved_fingerprint == fingerprint
                        or legacy_static_approval
                    )
                )

                if legacy_static_approval:
                    next_step["approval_fingerprint"] = fingerprint

                if not already_approved:
                    next_step["status"] = "AWAITING_APPROVAL"
                    next_step["approval_granted"] = False
                    next_step["approval_fingerprint"] = fingerprint
                    try:
                        if tool is None or validated_params is None:
                            raise ValueError(
                                "Tool parameters are not yet fully validated"
                            )
                        prompt = tool.confirmation_prompt(validated_params)
                        if selected_provider is not None:
                            prompt = (
                                f"{prompt} using "
                                f"{selected_provider.display_name}"
                            )
                        next_step["approval_prompt"] = prompt
                    except Exception:
                        next_step["approval_prompt"] = next_step.get(
                            "description", "this action"
                        )

                    awaiting_approval = next_step
                    self._save(workflow, steps)
                    self.db.commit()
                    break

            # Atomically claim the step before any external side effect.
            # A competing worker must not execute a step it failed to claim.
            claim_snapshot = deepcopy(steps)

            next_step["status"] = "EXECUTING"
            next_step["started_at"] = _now_iso()
            next_step["execution_started_at"] = next_step["started_at"]
            next_step["execution_id"] = str(uuid4())
            next_step["execution_attempt"] = int(
                next_step.get("execution_attempt", 0) or 0
            ) + 1
            next_step["checkpoint_version"] = 1
            # Claim the EXECUTING transition atomically before any
            # external side effect. Never invoke a tool if the claim was lost.
            if not self._compare_and_swap_steps(
                workflow, claim_snapshot, steps
            ):
                logger.info(
                    "Execution claim lost for workflow %s step %s; "
                    "another worker changed the workflow.",
                    workflow.id,
                    next_step.get("id"),
                )
                return {
                    "executed": executed,
                    "awaiting_approval": awaiting_approval,
                    "new_failures": new_failures,
                    "verified_steps": verified_steps,
                    "unverified_steps": unverified_steps,
                    "verification_failures": verification_failures,
                    "reconciliation_required_steps": sorted(
                        set(reconciliation_required_steps)
                    ),
                    "workflow_status": getattr(
                        workflow, "status", "IN_PROGRESS"
                    ),
                    "concurrency_conflict": True,
                }

            provider_attempts = next_step.setdefault("provider_attempts", [])
            failed_provider_ids = set()
            result = self._invoke_tool(next_step, params)
            executed.append(next_step["id"])

            if selected_provider is not None:
                provider_attempts.append({
                    "provider_id": selected_provider.provider_id,
                    "status": "COMPLETED" if result.get("success") else "FAILED",
                    "retry_safe": bool(result.get("retry_safe", False)),
                    "error": result.get("error"),
                    "attempted_at": _now_iso(),
                })

            # Fallback is restricted to explicitly retry-safe, non-mutating,
            # non-approval executions. Never change an approved target.
            side_effect_risk = bool(
                tool
                and (
                    getattr(tool, "is_mutating", False)
                    or getattr(tool, "requires_confirmation", False)
                )
            )
            can_fallback = (
                not result.get("success")
                and selection is not None
                and selected_provider is not None
                and result.get("retry_safe") is True
                and not side_effect_risk
                and not approval_required
            )

            while can_fallback:
                failed_provider_ids.add(selected_provider.provider_id.lower())
                candidate = selection.next_candidate(failed_provider_ids)
                if candidate is None:
                    break

                next_step["provider_id"] = candidate.provider_id
                next_step["provider_selection"] = {
                    "provider_id": candidate.provider_id,
                    "display_name": candidate.display_name,
                    "tool_name": candidate.tool_name,
                    "capability": candidate.capability,
                    "operation": next_step.get("provider_operation"),
                    "region": next_step.get("provider_region"),
                    "execution_status": candidate.execution_status,
                    "selected_at": _now_iso(),
                    "fallback_from": sorted(failed_provider_ids)[-1],
                }
                self._save(workflow, steps)
                self.db.commit()

                selected_provider = candidate
                result = self._invoke_tool(next_step, params)
                executed.append(next_step["id"])
                provider_attempts.append({
                    "provider_id": candidate.provider_id,
                    "status": "COMPLETED" if result.get("success") else "FAILED",
                    "retry_safe": bool(result.get("retry_safe", False)),
                    "error": result.get("error"),
                    "attempted_at": _now_iso(),
                })
                can_fallback = (
                    not result.get("success")
                    and result.get("retry_safe") is True
                )

            if result.get("success"):
                next_step["status"] = "COMPLETED"
                next_step["result"] = result.get("data")
                next_step["error"] = None
                verification = self._verify_tool_result(
                    next_step, params, result, workflow_id=workflow.id
                )
                next_step["verification"] = verification
                verification_status = verification.get("status")

                if verification_status == "VERIFIED":
                    verified_steps.append(next_step["id"])
                elif verification_status == "UNVERIFIED":
                    unverified_steps.append(next_step["id"])
                else:
                    verification_failures.append({
                        "step_id": next_step["id"],
                        "tool": next_step.get("tool"),
                        "verification": verification,
                    })
            else:
                failed_tool = self.registry.get(next_step.get("tool", ""))
                side_effect_risk = bool(
                    failed_tool
                    and (
                        getattr(failed_tool, "is_mutating", False)
                        or getattr(failed_tool, "requires_confirmation", False)
                    )
                )

                if side_effect_risk and not result.get("retry_safe", False):
                    next_step["status"] = "RECONCILIATION_REQUIRED"
                    next_step["reconciliation_reason"] = (
                        "mutating_tool_failure_outcome_uncertain"
                    )
                    next_step["reconciliation_required_at"] = _now_iso()
                    next_step["error"] = (
                        (result.get("error") or "Tool execution failed")
                        + " The action may have partially succeeded; "
                        "reconcile before retrying."
                    )
                    reconciliation_required_steps.append(next_step["id"])
                else:
                    next_step["status"] = "FAILED"
                    next_step["error"] = (
                        result.get("error") or "Tool execution failed"
                    )
                    new_failures.append(next_step)

            next_step["execution_finished_at"] = _now_iso()
            next_step["completed_at"] = next_step["execution_finished_at"]
            self._save(workflow, steps)
            self.db.commit()

        workflow.status = self._compute_overall_status(
            steps, awaiting_approval
        )
        self._save(workflow, steps)
        self.db.commit()

        goal = self.db.get(Goal, workflow.goal_id)
        if goal is not None:
            goal.status = workflow.status
            self.db.commit()

        return {
            "executed": executed,
            "awaiting_approval": awaiting_approval,
            "new_failures": new_failures,
            "verified_steps": verified_steps,
            "unverified_steps": unverified_steps,
            "verification_failures": verification_failures,
            "reconciliation_required_steps": sorted(
                set(reconciliation_required_steps)
            ),
            "workflow_status": workflow.status,
        }

    def _verify_tool_result(self, step: dict, params: dict, result: dict, workflow_id: int | None = None) -> dict:

        """Run an opt-in independent verifier; never infer verification from success."""

        tool = self.registry.get(step.get("tool", ""))

        if tool is None or type(tool).verify is BaseTool.verify:

            record = {

                "status": "UNVERIFIED",

                "method": None,

                "message": "Execution succeeded, but this tool has no independent verifier.",

                "evidence": {},

                "checked_at": _now_iso(),

            }

            try:

                self.db.add(ActionLog(

                    user_id=self.user.id,

                    action="workflow.outcome.unverified",

                    tool_name=step.get("tool"),

                    payload={"workflow_id": workflow_id, "step_id": step.get("id"), "verification": record},

                    result_status="warning",

                    result_message=record["message"],

                ))

                self.db.commit()

            except Exception:

                self.db.rollback()

            return record

        try:

            validated = tool.input_schema(**params)

            tool_result = ToolResult(

                success=True,

                message="",

                data=result.get("data") or {},

            )

            outcome = tool.verify(

                ToolContext(db=self.db, user=self.user), validated, tool_result

            )

            if outcome is None:

                status = "UNVERIFIED"

                message = "The tool did not provide independent verification evidence."

                method, evidence = None, {}

            else:

                verified = bool(outcome.get("verified"))

                status = "VERIFIED" if verified else "FAILED"

                message = "Persisted outcome matched the requested result." if verified else "Independent verification did not match the expected result."

                method = outcome.get("method")

                evidence = outcome.get("evidence") or {}

            record = {

                "status": status,

                "method": method,

                "message": message,

                "evidence": evidence,

                "checked_at": _now_iso(),

            }

            self.db.add(ActionLog(

                user_id=self.user.id,

                action="workflow.outcome.verified" if status == "VERIFIED" else "workflow.outcome.verification_incomplete",

                tool_name=step.get("tool"),

                payload={"workflow_id": workflow_id, "step_id": step.get("id"), "verification": record},

                result_status="success" if status == "VERIFIED" else "warning",

                result_message=message,

            ))

            self.db.commit()

            return record

        except Exception as exc:

            self.db.rollback()

            logger.exception("Outcome verification failed for %s", step.get("tool"))

            record = {

                "status": "FAILED",

                "method": "tool_verifier",

                "message": "Verification raised an error; the action may already have occurred. Do not retry automatically.",

                "evidence": {"error": str(exc)[:500]},

                "checked_at": _now_iso(),

            }

            try:

                self.db.add(ActionLog(

                    user_id=self.user.id,

                    action="workflow.outcome.verification_failed",

                    tool_name=step.get("tool"),

                    payload={"workflow_id": workflow_id, "step_id": step.get("id"), "verification": record},

                    result_status="warning",

                    result_message=record["message"],

                ))

                self.db.commit()

            except Exception:

                self.db.rollback()

            return record

    def _invoke_tool(self, step: dict, params: dict) -> dict:
        """Execute a workflow tool through its selected provider when supported."""
        tool_name = step.get("tool", "")
        tool = self.registry.get(tool_name)

        if tool is None:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "data": None,
                "retry_safe": False,
            }

        try:
            context = ToolContext(db=self.db, user=self.user)
            provider_id = step.get("provider_id")
            dispatch = self.registry.dispatch

            if provider_id:
                try:
                    signature = inspect.signature(dispatch)
                    supports_provider_id = (
                        "provider_id" in signature.parameters
                        or any(
                            parameter.kind == inspect.Parameter.VAR_KEYWORD
                            for parameter in signature.parameters.values()
                        )
                    )
                except (TypeError, ValueError):
                    supports_provider_id = True

                if supports_provider_id:
                    result = dispatch(
                        context,
                        tool_name,
                        params,
                        provider_id=provider_id,
                    )
                else:
                    # Compatibility for legacy registries. Never use this
                    # fallback for a mutating or confirmation-gated tool,
                    # because it cannot guarantee the approved provider.
                    if (
                        getattr(tool, "is_mutating", False)
                        or getattr(tool, "requires_confirmation", False)
                    ):
                        return {
                            "success": False,
                            "error": (
                                f"Registry dispatch cannot enforce selected "
                                f"provider '{provider_id}' for tool '{tool_name}'."
                            ),
                            "data": None,
                            "retry_safe": False,
                        }

                    result = dispatch(context, tool_name, params)
            else:
                result = dispatch(context, tool_name, params)

            return {
                "success": result.success,
                "error": None if result.success else result.message,
                "data": result.data,
                "retry_safe": bool(getattr(result, "retry_safe", False)),
            }

        except Exception as exc:
            logger.exception("Tool %s raised an exception", tool_name)
            return {
                "success": False,
                "error": str(exc),
                "data": None,
                "retry_safe": False,
            }

    def _compute_overall_status(self, steps: list[dict], awaiting: Optional[dict]) -> str:

        if awaiting:

            return "AWAITING_APPROVAL"

        if any(step.get("status") in {"EXECUTING", "PENDING", "READY", "APPROVED"} for step in steps):

            return "IN_PROGRESS"

        required = [step for step in steps if step.get("required", True)]

        optional = [step for step in steps if not step.get("required", True)]

        if any(step.get("status") == "REJECTED" for step in required):

            return "REJECTED"

        reconciliation_pending = any(

            step.get("status") == "RECONCILIATION_REQUIRED"

            for step in steps

        )

        if reconciliation_pending:

            return "PARTIALLY_COMPLETED"

        required_failed = [

            step for step in required

            if step.get("status") in {"FAILED", "BLOCKED", "CANCELLED"}

        ]

        required_done = [step for step in required if step.get("status") == "COMPLETED"]

        optional_incomplete = [

            step for step in optional

            if step.get("status") in {"FAILED", "BLOCKED", "CANCELLED", "REJECTED"}

        ]

        if required_failed:

            return "PARTIALLY_COMPLETED" if required_done else "FAILED"

        verification_failed = any(

            step.get("verification", {}).get("status") == "FAILED"

            for step in steps

        )

        if optional_incomplete or verification_failed:

            return "PARTIALLY_COMPLETED"

        if required and all(step.get("status") == "COMPLETED" for step in required):

            return "COMPLETED"

        if not required and not optional:

            return "COMPLETED"

        if optional and all(step.get("status") in {"COMPLETED", "SKIPPED"} for step in optional):

            return "COMPLETED"

        return "CANCELLED"

    def approve_step(self, workflow: Workflow, step_id: str) -> bool:
        steps = self._steps(workflow)
        old_steps = deepcopy(steps)
        target = next((step for step in steps if step.get("id") == step_id), None)

        if target is None or target.get("status") != "AWAITING_APPROVAL":
            return False

        target["approval_granted"] = True
        target["status"] = "APPROVED"

        if not self._compare_and_swap_steps(workflow, old_steps, steps):
            return False

        self._audit(
            "workflow.step.approved",
            target,
            f"User approved workflow {workflow.id} step {step_id}.",
            workflow.id,
        )
        self.db.commit()
        return True


    def reject_step(
        self,
        workflow: Workflow,
        step_id: str,
        reason: str = "Rejected by user",
    ) -> bool:
        steps = self._steps(workflow)
        old_steps = deepcopy(steps)
        target = next((step for step in steps if step.get("id") == step_id), None)

        if target is None or target.get("status") != "AWAITING_APPROVAL":
            return False

        target["status"] = "REJECTED"
        target["error"] = (reason or "Rejected by user")[:1000]
        target["rejected_at"] = _now_iso()

        if not self._compare_and_swap_steps(workflow, old_steps, steps):
            return False

        workflow.status = self._compute_overall_status(steps, None)
        self._audit(
            "workflow.step.rejected",
            target,
            f"User rejected workflow {workflow.id} step {step_id}.",
            workflow.id,
        )
        self.db.commit()
        return True


    def retry_step(self, workflow: Workflow, step_id: str) -> dict:

        steps = self._steps(workflow)
        old_steps = deepcopy(steps)
        target = next((step for step in steps if step.get("id") == step_id), None)

        if target is None:

            return {"ok": False, "reason": "Step not found"}

        if target.get("status") == "RECONCILIATION_REQUIRED":
            return {
                "ok": False,
                "reason": "Outcome is uncertain; reconcile the side effect before retrying",
            }

        if target.get("status") != "FAILED":
            return {
                "ok": False,
                "reason": f"Step is {target.get('status')}, not FAILED",
            }

        retries = int(target.get("retry_count", 0) or 0)
        max_retries = int(target.get("max_retries", 1) or 0)

        if retries >= max_retries:

            return {"ok": False, "reason": "Max retries exceeded"}

        target["status"] = "PENDING"

        target["error"] = None
        target["retry_count"] = retries + 1
        target.pop("completed_at", None)

        target.pop("completed_at", None)

        for step in steps:
            if (
                step_id in step.get("depends_on", [])
                and step.get("status") == "BLOCKED"
            ):
                step["status"] = "PENDING"

                step["error"] = None

        if not self._compare_and_swap_steps(workflow, old_steps, steps):
            return {
                "ok": False,
                "reason": "Workflow changed concurrently; reload and retry",
            }

        workflow.status = "IN_PROGRESS"
        self._audit(
            "workflow.step.retried",
            target,
            f"User requested retry {target['retry_count']} for workflow "
            f"{workflow.id} step {step_id}.",
            workflow.id,
        )
        self.db.commit()

        return {"ok": True, "retry_count": target["retry_count"]}
