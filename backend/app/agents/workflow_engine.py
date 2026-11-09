"""Workflow engine with failure isolation, partial compilation and retry support."""
from __future__ import annotations
import logging
import copy
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import update
from sqlalchemy.orm import object_session

from app.models import User, Workflow, Goal, ActionLog
from app.schemas.workflow import WorkflowPlan
from app.tools.base import ToolContext
from app.tools.registry import registry

logger = logging.getLogger(__name__)

TERMINAL_STATES = {"COMPLETED", "FAILED", "SKIPPED", "BLOCKED", "CANCELLED", "REJECTED"}


def _is_aggregation_tool(step: dict) -> bool:
    """Detect aggregation/summary steps that should tolerate upstream failures."""
    tool_name = str(step.get("tool", "")).lower()
    desc = str(step.get("description", "")).lower()
    return (
        "compile" in tool_name or "summary" in tool_name or
        "compile" in desc or "summary" in desc
    )


class WorkflowEngine:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    # ─── Creation ─────────────────────────────────────────────

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

        steps = [s.model_dump(mode="json") for s in plan.steps]
        for s in steps:
            s.setdefault("status", "PENDING")
            s.setdefault("depends_on", [])
            s.setdefault("required", True)
            s.setdefault("retry_count", 0)
            s.setdefault("max_retries", 1)

            # Safety policy is derived from server-side tool metadata, never
            # trusted solely from an LLM-generated workflow step.
            tool = registry.get(s.get("tool", ""))
            if tool and (
                getattr(tool, "requires_confirmation", False)
                or getattr(tool, "is_mutating", False)
            ):
                s["approval_required"] = True
                try:
                    validated = tool.input_schema(**(s.get("params") or {}))
                    s["approval_prompt"] = tool.confirmation_prompt(validated)
                except Exception:
                    s["approval_prompt"] = s.get("description", "this action")

            # Force tolerate_failure on aggregation steps.
            if _is_aggregation_tool(s):
                s["dep_policy"] = "tolerate_failure"
                s["required"] = True
            else:
                s.setdefault("dep_policy", "all_success")

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

    # ─── Helpers ──────────────────────────────────────────────

    def _steps(self, workflow: Workflow) -> list[dict]:
        # Return detached data so nested JSON mutations are detected
        # when _save assigns the updated value to the ORM model.
        return copy.deepcopy(workflow.steps_json or [])

    def _save(self, workflow: Workflow, steps: list[dict]):
        # SQLAlchemy's plain JSON type does not reliably track nested in-place
        # mutations. Assign a fresh object so completion/failure transitions
        # are persisted after a step has been claimed and the ORM refreshed.
        workflow.steps_json = copy.deepcopy(steps)
        workflow.updated_at = datetime.utcnow()

    def _audit(self, action: str, step: dict, message: str, workflow_id: int | None = None) -> None:
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
        self, workflow: Workflow, old_steps: list[dict], new_steps: list[dict]
    ) -> bool:
        """
        Atomically persist a step-state transition for a real SQLAlchemy session.

        SQLite (the development/test database) and PostgreSQL JSONB-like dialect
        behavior differ; the current model uses SQLAlchemy JSON. The CAS predicate
        is supported by SQLite's JSON text storage. For other dialects, use row
        locking in the deployment migration before enabling concurrent workers.
        """
        if not isinstance(self.db, Session):
            # Unit tests and transient workflow objects use the in-memory path.
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
            .values(steps_json=new_steps, updated_at=datetime.utcnow())
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
        return {s["id"]: s.get("status", "PENDING") for s in steps}

    def _is_ready(self, step: dict, status_map: dict[str, str]) -> bool:
        deps = step.get("depends_on", [])
        return all(status_map.get(d) in TERMINAL_STATES for d in deps)

    def _should_block(self, step: dict, status_map: dict[str, str]) -> tuple[bool, str]:
        # ABSOLUTE RULE: Compile/Summary steps NEVER block.
        if _is_aggregation_tool(step):
            return False, ""

        deps = step.get("depends_on", [])
        policy = step.get("dep_policy", "all_success")
        for d in deps:
            dstate = status_map.get(d)
            if dstate in ("FAILED", "BLOCKED", "REJECTED") and policy == "all_success":
                return True, f"dependency '{d}' failed"
        return False, ""

    def _inject_dependency_results(self, step: dict, steps: list[dict]) -> dict:
        params = dict(step.get("params") or {})
        if not _is_aggregation_tool(step):
            return params

        dep_results = {}
        for s in steps:
            if s["id"] in step.get("depends_on", []) and s.get("status") == "COMPLETED":
                dep_results[s["id"]] = {"tool": s.get("tool"), "result": s.get("result")}

        dep_failures = {}
        for s in steps:
            if s["id"] in step.get("depends_on", []) and s.get("status") in ("FAILED", "BLOCKED", "REJECTED"):
                dep_failures[s["id"]] = {"tool": s.get("tool"), "error": s.get("error")}

        params["dependency_results"] = dep_results
        params["dependency_failures"] = dep_failures
        return params
    # ─── Execution ────────────────────────────────────────────

    def execute(self, workflow: Workflow, max_steps: int = 20) -> dict:
        steps = self._steps(workflow)
        executed: list[str] = []
        new_failures: list[dict] = []
        awaiting_approval: Optional[dict] = None

        for _ in range(max_steps):
            status_map = self._status_map(steps)

            next_step = None
            for s in steps:
                # APPROVED is a runnable state. Previously approve_step() set
                # this value, but execute() ignored it, so approved actions
                # could never run.
                if s.get("status") not in ("PENDING", "READY", "APPROVED"):
                    continue
                if not self._is_ready(s, status_map):
                    continue

                blocked, reason = self._should_block(s, status_map)
                if blocked:
                    s["status"] = "BLOCKED"
                    s["error"] = f"Blocked: {reason}"
                    continue

                next_step = s
                break

            if next_step is None:
                break

            registered_tool = registry.get(next_step.get("tool", ""))
            tool_requires_approval = bool(
                registered_tool
                and (
                    getattr(registered_tool, "requires_confirmation", False)
                    or getattr(registered_tool, "is_mutating", False)
                )
            )
            requires_approval = bool(
                next_step.get("approval_required") or tool_requires_approval
            )

            if requires_approval and next_step.get("status") != "APPROVED":
                next_step["approval_required"] = True
                if registered_tool and not next_step.get("approval_prompt"):
                    try:
                        validated = registered_tool.input_schema(
                            **(next_step.get("params") or {})
                        )
                        next_step["approval_prompt"] = (
                            registered_tool.confirmation_prompt(validated)
                        )
                    except Exception:
                        pass
                old_steps = copy.deepcopy(steps)
                next_step["status"] = "AWAITING_APPROVAL"
                awaiting_approval = next_step
                if not self._compare_and_swap_steps(workflow, old_steps, steps):
                    steps = self._steps(workflow)
                    awaiting_approval = None
                    continue
                steps = self._steps(workflow)
                break

            old_steps = copy.deepcopy(steps)
            next_step["status"] = "EXECUTING"
            next_step["started_at"] = datetime.utcnow().isoformat()
            if not self._compare_and_swap_steps(workflow, old_steps, steps):
                steps = self._steps(workflow)
                continue
            steps = self._steps(workflow)
            # Re-resolve the claimed step from the committed state.
            next_step = next(s for s in steps if s["id"] == next_step["id"])

            params = self._inject_dependency_results(next_step, steps)
            result = self._invoke_tool(next_step, params)
            executed.append(next_step["id"])

            if result["success"]:
                next_step["status"] = "COMPLETED"
                next_step["result"] = result["data"]
                next_step["completed_at"] = datetime.utcnow().isoformat()
            else:
                next_step["status"] = "FAILED"
                next_step["error"] = result["error"]
                next_step["completed_at"] = datetime.utcnow().isoformat()
                new_failures.append(next_step)

            self._save(workflow, steps)
            self.db.commit()

        workflow.status = self._compute_overall_status(steps, awaiting_approval)
        self._save(workflow, steps)
        self.db.commit()

        goal = self.db.get(Goal, workflow.goal_id)
        if goal:
            goal.status = workflow.status
            self.db.commit()

        return {
            "executed": executed,
            "awaiting_approval": awaiting_approval,
            "new_failures": new_failures,
            "workflow_status": workflow.status,
        }

    def _invoke_tool(self, step: dict, params: dict) -> dict:
        tool_name = step.get("tool", "")
        tool = registry.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"Unknown tool: {tool_name}", "data": None}

        try:
            ctx = ToolContext(db=self.db, user=self.user)
            result = registry.dispatch(ctx, tool_name, params)
            return {
                "success": result.success,
                "error": None if result.success else result.message,
                "data": result.data,
            }
        except Exception as e:
            logger.exception(f"Tool {tool_name} raised: {e}")
            return {"success": False, "error": str(e), "data": None}

    def _compute_overall_status(self, steps: list[dict], awaiting: Optional[dict]) -> str:
        if awaiting:
            return "AWAITING_APPROVAL"

        if any(
            s.get("status") in ("EXECUTING", "PENDING", "READY", "APPROVED")
            for s in steps
        ):
            return "IN_PROGRESS"

        required = [s for s in steps if s.get("required", True)]
        optional = [s for s in steps if not s.get("required", True)]

        required_done = [s for s in required if s.get("status") == "COMPLETED"]
        required_failed = [s for s in required if s.get("status") in ("FAILED", "BLOCKED", "REJECTED")]
        required_rejected = [s for s in required if s.get("status") == "REJECTED"]

        if required and not required_failed:
            if any(s.get("status") in ("FAILED", "REJECTED") for s in optional):
                return "PARTIALLY_COMPLETED"
            return "COMPLETED"

        if required_done and required_failed:
            return "PARTIALLY_COMPLETED"

        if required_failed and not required_done:
            return "REJECTED" if required_rejected and len(required_rejected) == len(required_failed) else "FAILED"

        return "CANCELLED"

    # ─── Approvals & Retries ──────────────────────────────────

    def approve_step(self, workflow: Workflow, step_id: str) -> bool:
        steps = self._steps(workflow)
        old_steps = copy.deepcopy(steps)
        target = next((s for s in steps if s.get("id") == step_id), None)
        if target is None or target.get("status") != "AWAITING_APPROVAL":
            return False
        target["status"] = "APPROVED"
        if not self._compare_and_swap_steps(workflow, old_steps, steps):
            return False
        self._audit(
            "workflow.step.approved", target,
            f"User approved workflow {workflow.id} step {step_id}.",
            workflow.id,
        )
        self.db.commit()
        return True

    def reject_step(
        self, workflow: Workflow, step_id: str, reason: str | None = None
    ) -> bool:
        steps = self._steps(workflow)
        old_steps = copy.deepcopy(steps)
        target = next((s for s in steps if s.get("id") == step_id), None)
        if target is None or target.get("status") != "AWAITING_APPROVAL":
            return False
        target["status"] = "REJECTED"
        target["error"] = (reason or "Rejected by user.")[:1000]
        target["completed_at"] = datetime.utcnow().isoformat()
        if not self._compare_and_swap_steps(workflow, old_steps, steps):
            return False
        workflow.status = self._compute_overall_status(steps, None)
        self._audit(
            "workflow.step.rejected", target,
            f"User rejected workflow {workflow.id} step {step_id}.",
            workflow.id,
        )
        self.db.commit()
        return True

    def retry_step(self, workflow: Workflow, step_id: str) -> dict:
        steps = self._steps(workflow)
        old_steps = copy.deepcopy(steps)
        target = next((s for s in steps if s.get("id") == step_id), None)
        if target is None:
            return {"ok": False, "reason": "Step not found"}
        if target.get("status") != "FAILED":
            return {"ok": False, "reason": f"Step is {target.get('status')}, not FAILED"}
        retries = int(target.get("retry_count", 0))
        max_retries = int(target.get("max_retries", 1))
        if retries >= max_retries:
            return {"ok": False, "reason": "Max retries exceeded"}

        target["status"] = "PENDING"
        target["error"] = None
        target["completed_at"] = None
        target["retry_count"] = retries + 1

        for step in steps:
            if step_id in step.get("depends_on", []) and step.get("status") == "BLOCKED":
                step["status"] = "PENDING"
                step["error"] = None

        workflow.status = "IN_PROGRESS"
        if not self._compare_and_swap_steps(workflow, old_steps, steps):
            return {"ok": False, "reason": "Workflow changed concurrently; reload and retry"}
        self._audit(
            "workflow.step.retried", target,
            f"User requested retry {target['retry_count']} for workflow {workflow.id} step {step_id}.",
            workflow.id,
        )
        self.db.commit()
        return {"ok": True, "retry_count": target["retry_count"]}
