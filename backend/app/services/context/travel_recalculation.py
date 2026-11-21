"""Evidence-aware dispatcher for pending travel recalculations.

Searches are executed only through the existing WorkflowEngine and registered
ToolRegistry. Booking/purchase/mutating tools are never auto-executed here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.agents.workflow_engine import WorkflowEngine
from app.models import Conversation, Workflow
from app.schemas.workflow import WorkflowPlan, WorkflowStep
from app.services.context.travel_mission import MISSION_KEY, TravelMission
from app.services.context.travel_feasibility import evaluate_travel_feasibility
from app.tools.registry import registry as default_registry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_FALLBACK_TOOLS = {
    "flights": "search_flights_real",
    "hotels": "search_hotels_stayapi",
    "transfers": "get_cab_links",
    "routes": "optimize_route",
    "itinerary": "generate_advanced_itinerary",
}


def _trip_days(constraints: dict[str, Any]) -> int | None:
    value = constraints.get("trip_days")
    if isinstance(value, int) and 1 <= value <= 14:
        return value
    start = constraints.get("departure_date")
    end = constraints.get("return_date")
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        return days if 1 <= days <= 14 else None
    except (TypeError, ValueError):
        return None


def _derive_params(artifact: str, raw: dict[str, Any], mission: dict[str, Any]) -> tuple[str | None, dict[str, Any], str | None]:
    constraints = mission.get("constraints") or {}
    selections = mission.get("selections") or {}
    params = deepcopy(raw) if isinstance(raw, dict) else {}
    tool_name = str(params.pop("__tool_name__", "") or "")

    if artifact == "flights":
        tool_name = tool_name or _FALLBACK_TOOLS[artifact]
        params.setdefault("origin", constraints.get("origin"))
        params.setdefault("destination", constraints.get("destination"))
        params.setdefault("date", constraints.get("departure_date"))
        travellers = constraints.get("travellers")
        if "adults" not in params and travellers == 1:
            params["adults"] = 1
        if constraints.get("cabin") and "travel_class" not in params:
            cabin = str(constraints["cabin"]).lower()
            params["travel_class"] = {
                "economy": 1, "premium economy": 2,
                "business": 3, "business class": 3,
                "first": 4, "first class": 4,
            }.get(cabin)
        if constraints.get("direct_only") is True:
            params.setdefault("max_stops", 0)
        if "adults" not in params and travellers != 1:
            return tool_name, params, "Passenger composition is not stored. Please specify the adult and child counts before refreshing this flight search."
        if not params.get("origin") or not params.get("destination") or not params.get("date"):
            return tool_name, params, "Flight origin, destination and departure date are required to refresh this search."

    elif artifact == "hotels":
        tool_name = tool_name or _FALLBACK_TOOLS[artifact]
        params.setdefault("city", constraints.get("destination"))
        params.setdefault("check_in", constraints.get("check_in") or constraints.get("departure_date"))
        params.setdefault("check_out", constraints.get("check_out") or constraints.get("return_date"))
        if constraints.get("travellers") is not None:
            params.setdefault("travellers", constraints["travellers"])
        if not params.get("city") or not params.get("check_in") or not params.get("check_out"):
            return tool_name, params, "Hotel city, check-in and check-out dates are required; the search was not guessed."
        if params.get("travellers") is None:
            return tool_name, params, "The traveller count is unknown; please provide it before refreshing this hotel search."

    elif artifact == "transfers":
        tool_name = tool_name or _FALLBACK_TOOLS[artifact]
        if tool_name == "get_cab_links":
            flight_record = selections.get("flights") or {}
            flight = flight_record.get("candidate") if isinstance(flight_record, dict) else None
            hotel_record = selections.get("hotels") or {}
            hotel = hotel_record.get("candidate") if isinstance(hotel_record, dict) else None
            segments = flight.get("segments") if isinstance(flight, dict) else None
            if segments and isinstance(segments[-1], dict):
                params.setdefault("pickup_location", segments[-1].get("destination"))
            if isinstance(hotel, dict):
                hotel_destination = hotel.get("address") or hotel.get("name") or hotel.get("hotel_name")
                params.setdefault("dropoff_location", hotel_destination)
        if not params.get("pickup_location") or not params.get("dropoff_location"):
            return tool_name, params, "Transfer pickup and drop-off locations are not both known. Select a flight and hotel or provide both locations."

    elif artifact == "itinerary":
        tool_name = tool_name or _FALLBACK_TOOLS[artifact]
        params.setdefault("destination", constraints.get("destination"))
        params.setdefault("days", _trip_days(constraints))
        if constraints.get("origin"):
            params.setdefault("origin", constraints["origin"])
        if constraints.get("travellers") is not None:
            params.setdefault("travellers", constraints["travellers"])
        if constraints.get("budget_amount") is not None:
            params.setdefault("budget", constraints["budget_amount"])
        check_in = constraints.get("check_in") or constraints.get("departure_date")
        check_out = constraints.get("check_out") or constraints.get("return_date")
        if check_in and check_out:
            params.setdefault("check_in", check_in)
            params.setdefault("check_out", check_out)
        if not params.get("destination") or not params.get("days"):
            return tool_name, params, "An explicit destination and trip duration (or return date) are required to regenerate the itinerary."

    elif artifact == "routes":
        tool_name = tool_name or _FALLBACK_TOOLS[artifact]
        if not isinstance(params.get("places"), list) or len(params["places"]) < 2:
            return tool_name, params, "Route recalculation requires at least two previously recorded places with coordinates."

    else:
        return None, params, f"No safe recalculation handler exists for artifact '{artifact}'."

    return tool_name, params, None


def prepare_recalculation_steps(mission: dict[str, Any], registry: Any = None) -> dict[str, Any]:
    """Pure planning/validation stage; does not call tools or mutate mission."""
    registry = registry or default_registry
    steps: list[WorkflowStep] = []
    blocked: list[dict[str, Any]] = []
    local_completed: list[str] = []
    seen_search_artifacts: set[str] = set()

    for item in mission.get("pending_recalculations") or []:
        if not isinstance(item, dict) or item.get("status", "pending") != "pending":
            continue
        artifact = str(item.get("artifact") or "")
        queue_id = str(item.get("queue_id") or uuid4())
        if artifact == "budget":
            # Budget is recomputed from current evidence, never via the legacy
            # CalculateBudgetTool whose missing inputs default to zero.
            local_completed.append(queue_id)
            continue

        raw = deepcopy(item.get("params") or {})
        if not isinstance(raw, dict):
            raw = {}
        saved_tool = str(item.get("tool_name") or "")
        if saved_tool:
            raw["__tool_name__"] = saved_tool

        # Safety gate must run before artifact-specific completeness checks.
        # An unsafe tool remains blocked even when its query parameters are
        # also incomplete; missing fields must never mask a mutability hazard.
        candidate_tool_name = saved_tool or _FALLBACK_TOOLS.get(artifact, "")
        candidate_tool = registry.get(candidate_tool_name) if candidate_tool_name else None
        if candidate_tool is None:
            blocked.append({
                "queue_id": queue_id,
                "artifact": artifact,
                "reason": f"Registered tool '{candidate_tool_name or artifact}' is unavailable.",
            })
            continue
        if getattr(candidate_tool, "requires_confirmation", False) or getattr(candidate_tool, "is_mutating", False):
            blocked.append({
                "queue_id": queue_id,
                "artifact": artifact,
                "reason": "This tool is mutating or confirmation-gated and cannot run in automatic recalculation.",
            })
            continue

        tool_name, params, reason = _derive_params(artifact, raw, mission)
        if reason:
            blocked.append({"queue_id": queue_id, "artifact": artifact, "reason": reason})
            continue
        tool = registry.get(tool_name or "") if tool_name else None
        if tool is None:
            blocked.append({"queue_id": queue_id, "artifact": artifact, "reason": f"Registered tool '{tool_name}' is unavailable."})
            continue
        # Re-check the resolved tool too, in case derivation selected a different
        # handler from the fallback/saved name.
        if getattr(tool, "requires_confirmation", False) or getattr(tool, "is_mutating", False):
            blocked.append({
                "queue_id": queue_id,
                "artifact": artifact,
                "reason": "This tool is mutating or confirmation-gated and cannot run in automatic recalculation.",
            })
            continue
        try:
            validated = tool.input_schema(**params)
            normalized = validated.model_dump(mode="json") if hasattr(validated, "model_dump") else dict(params)
        except (ValidationError, TypeError, ValueError) as exc:
            errors = exc.errors() if isinstance(exc, ValidationError) else []
            missing = [".".join(str(part) for part in err.get("loc", ())) for err in errors if err.get("type") == "missing"]
            detail = "Required inputs are missing: " + ", ".join(missing) if missing else str(exc)[:400]
            blocked.append({"queue_id": queue_id, "artifact": artifact, "reason": detail})
            continue

        if artifact in seen_search_artifacts:
            blocked.append({
                "queue_id": queue_id,
                "artifact": artifact,
                "reason": "A recalculation for this artifact is already queued; the duplicate task was suppressed.",
            })
            continue

        seen_search_artifacts.add(artifact)
        item["queue_id"] = queue_id
        steps.append(WorkflowStep(
            id=f"travel-recalc-{queue_id}",
            description=f"Refresh {artifact} evidence after a travel mission change",
            tool=tool_name,
            params=normalized,
            required=True,
            max_retries=0,
        ))

    return {"steps": steps, "blocked": blocked, "local_completed": local_completed}




def dispatch_pending_travel_recalculations(
    db: Any,
    user: Any,
    conversation: Conversation,
    *,
    registry: Any = None,
) -> dict[str, Any] | None:
    """Dispatch pending safe searches through WorkflowEngine and persist outcome."""
    registry = registry or default_registry
    state = dict(getattr(conversation, "state_json", None) or {})
    raw_mission = state.get(MISSION_KEY)
    if not isinstance(raw_mission, dict):
        return None
    mission = TravelMission.model_validate(raw_mission)
    if not any(isinstance(x, dict) and x.get("status", "pending") == "pending" for x in mission.pending_recalculations):
        return None
    # Selected-flight invalidation predates queue IDs; assign IDs on the live
    # mission object before preparing workflow steps so status updates remain
    # correlated even for those legacy queue records.
    for queued in mission.pending_recalculations:
        if isinstance(queued, dict) and queued.get("status", "pending") == "pending":
            queued.setdefault("queue_id", str(uuid4()))

    # Never compete with a separately active user workflow.
    active_id = state.get("active_workflow_id")
    if active_id:
        active = db.get(Workflow, active_id)
        if active and active.user_id == user.id and active.status in {
            "PLANNED", "IN_PROGRESS", "EXECUTING", "AWAITING_APPROVAL", "PARTIALLY_COMPLETED"
        }:
            return {"status": "deferred", "reason": "Another workflow is active; travel refreshes remain queued."}

    prepared = prepare_recalculation_steps(mission.model_dump(mode="json"), registry)
    queue_by_id = {str(x.get("queue_id")): x for x in mission.pending_recalculations if isinstance(x, dict)}

    for item in prepared["blocked"]:
        queued = queue_by_id.get(str(item.get("queue_id")))
        if queued is not None:
            queued["status"] = "blocked"
            queued["blocked_reason"] = item["reason"]
            queued["updated_at"] = _now()

    local_ids = set(prepared["local_completed"])
    if local_ids:
        mission.pending_recalculations = [
            x for x in mission.pending_recalculations
            if not (isinstance(x, dict) and (str(x.get("queue_id") or x.get("artifact")) in local_ids))
        ]

    # Bound one dispatcher run; WorkflowEngine also has a bounded step loop.
    # Remaining queue entries stay pending for a later user turn.
    steps = prepared["steps"][:10]
    if not steps:
        mission.feasibility = evaluate_travel_feasibility(mission.model_dump(mode="json"))
        mission.updated_at = _now()
        state[MISSION_KEY] = mission.model_dump(mode="json")
        report = {
            "status": "completed_locally" if local_ids else "blocked",
            "completed_locally": sorted(local_ids),
            "blocked": prepared["blocked"],
            "feasibility": mission.feasibility,
        }
        state["last_travel_recalculation"] = report
        conversation.state_json = state
        db.commit()
        return report

    # Mark queue entries before creating the workflow to avoid duplicate dispatch.
    queue_ids = []
    step_to_queue = {}
    for step in steps:
        queue_id = step.id.removeprefix("travel-recalc-")
        queue_ids.append(queue_id)
        step_to_queue[step.id] = queue_id
        queued = queue_by_id.get(queue_id)
        if queued is not None:
            queued["status"] = "dispatching"
            queued["workflow_id"] = None
            queued["updated_at"] = _now()

    mission_data = mission.model_dump(mode="json")
    context = {"travel_recalculation": {
        "mission_id": mission.mission_id,
        "mission_version": mission.version,
        "queue_ids": queue_ids,
        "step_to_queue": step_to_queue,
    }}
    state[MISSION_KEY] = mission_data
    conversation.state_json = state
    db.commit()

    try:
        plan = WorkflowPlan(
            goal_title="Refresh travel mission evidence",
            goal_description="Recalculate only stale, safe travel artifacts using their validated original search parameters.",
            context=context,
            steps=steps,
        )
        engine = WorkflowEngine(db, user, tool_registry=registry)
        workflow = engine.create_workflow(conversation.id, plan)
        for queue_id in queue_ids:
            queued = next((x for x in mission.pending_recalculations if isinstance(x, dict) and str(x.get("queue_id")) == queue_id), None)
            if queued is not None:
                queued["status"] = "running"
                queued["workflow_id"] = workflow.id
        state = dict(getattr(conversation, "state_json", None) or {})
        state[MISSION_KEY] = mission.model_dump(mode="json")
        state["travel_recalculation_workflow_id"] = workflow.id
        conversation.state_json = state
        db.commit()

        execution = engine.execute(workflow)
        steps_after = {str(x.get("id")): x for x in (workflow.steps_json or [])}
        state = dict(getattr(conversation, "state_json", None) or {})
        current_raw = state.get(MISSION_KEY)
        current = TravelMission.model_validate(current_raw) if isinstance(current_raw, dict) else None
        if current is not None:
            for step_id, queue_id in step_to_queue.items():
                step_data = steps_after.get(step_id) or {}
                queued = next((x for x in current.pending_recalculations if isinstance(x, dict) and str(x.get("queue_id")) == queue_id), None)
                if queued is None:
                    continue  # Fresh evidence capture already removed the task.
                status = step_data.get("status")
                if status in {"FAILED", "BLOCKED", "SKIPPED", "RECONCILIATION_REQUIRED"}:
                    queued["status"] = "blocked"
                    queued["blocked_reason"] = step_data.get("error") or f"Workflow step ended with {status}."
                elif status == "AWAITING_APPROVAL":
                    queued["status"] = "awaiting_approval"
                    queued["blocked_reason"] = "The workflow requires explicit user approval."
                elif status == "COMPLETED":
                    # Evidence capture may have rejected an outdated result. If
                    # the mission is unchanged, this was an unattachable result
                    # (for example, an empty route), so do not loop forever.
                    if current.version != mission.version or current.mission_id != mission.mission_id:
                        queued["status"] = "pending"
                        queued["blocked_reason"] = "Mission changed during execution; retry against the new mission snapshot."
                    else:
                        artifact_name = str(queued.get("artifact") or "")
                        artifact_state = (current.artifacts or {}).get(artifact_name) or {}
                        if artifact_state.get("status") == "handoff":
                            # The tool completed by producing an external handoff.
                            # This resolves the dispatcher task, but it is not live
                            # inventory and must never be promoted to current evidence.
                            queued["status"] = "handoff"
                            queued["result_status"] = "external_handoff"
                            queued["reason"] = (
                                "An external handoff was prepared. No live inventory, "
                                "reservation or booking was performed. User action is required."
                            )
                            artifact_evidence = artifact_state.get("evidence") or {}
                            queued["handoff_url"] = artifact_evidence.get("search_url")
                            candidates = (current.candidates or {}).get(artifact_name) or []
                            first_candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
                            links = first_candidate.get("links") or {}
                            queued["handoff_links"] = deepcopy(links) if isinstance(links, dict) else {}
                            queued["updated_at"] = _now()
                        else:
                            queued["status"] = "blocked"
                            queued["blocked_reason"] = "Tool completed but returned no attachable normalized evidence."
            current.feasibility = evaluate_travel_feasibility(current.model_dump(mode="json"))
            current.updated_at = _now()
            state[MISSION_KEY] = current.model_dump(mode="json")
        report = {
            "status": execution.get("workflow_status", workflow.status),
            "workflow_id": workflow.id,
            "executed_steps": execution.get("executed", []),
            "awaiting_approval": execution.get("awaiting_approval"),
            "blocked": prepared["blocked"],
            "feasibility": current.feasibility if current is not None else None,
        }
        state["last_travel_recalculation"] = report
        conversation.state_json = state
        db.commit()
        return report
    except Exception as exc:
        db.rollback()
        state = dict(getattr(conversation, "state_json", None) or {})
        current_raw = state.get(MISSION_KEY)
        if isinstance(current_raw, dict):
            current = TravelMission.model_validate(current_raw)
            for item in current.pending_recalculations:
                if isinstance(item, dict) and str(item.get("queue_id")) in set(queue_ids):
                    item["status"] = "blocked"
                    item["blocked_reason"] = f"Recalculation workflow could not start: {type(exc).__name__}: {str(exc)[:250]}"
            current.feasibility = evaluate_travel_feasibility(current.model_dump(mode="json"))
            state[MISSION_KEY] = current.model_dump(mode="json")
        report = {"status": "blocked", "blocked": prepared["blocked"], "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        state["last_travel_recalculation"] = report
        conversation.state_json = state
        db.commit()
        return report
