"""Runtime verification for Phase 2C travel evidence recalculation.

All tool responses are deterministic fixtures. The real WorkflowEngine, SQLAlchemy
models/session, dispatcher and evidence-capture path are exercised; no network or
provider API is invoked.
"""
from __future__ import annotations

from datetime import datetime

from copy import deepcopy

from pydantic import BaseModel

from app.models import Conversation, User, Workflow
from app.services.context.travel_feasibility import evaluate_travel_feasibility
from app.services.context.travel_mission import (
    MISSION_KEY,
    TravelMission,
    _select_flight_candidate,
)
from app.services.context.travel_recalculation import (
    dispatch_pending_travel_recalculations,
)
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.tools.travel_apis import HotelInput


class _FakeHotelSearchTool(BaseTool):
    name = "search_hotels_stayapi"
    description = "Deterministic fake hotel search for runtime tests."
    input_schema = HotelInput
    capability = "travel"
    provider_adapters = ()
    requires_confirmation = False
    is_mutating = False

    def __init__(self, callback):
        self.callback = callback
        self.calls = []

    def execute(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        self.calls.append(params.model_dump(mode="json"))
        return self.callback(ctx, params)


class _FakeRegistry:
    """Small registry contract used by WorkflowEngine; dispatch never uses I/O."""

    def __init__(self, tool):
        tools = tool if isinstance(tool, (list, tuple)) else [tool]
        self.tools = {item.name: item for item in tools}

    def get(self, name):
        return self.tools.get(name)

    def list_tools(self):
        return sorted(self.tools)

    def dispatch(self, context, name, params, provider_id=None):
        tool = self.get(name)
        if tool is None:
            return ToolResult(False, f"Unknown test tool: {name}", {})
        validated = tool.input_schema(**params)
        return tool.execute(context, validated)


def _fresh_hotel_payload():
    return {
        "type": "hotel_list",
        "provider": "runtime_test_fixture",
        "live_inventory": True,
        "retrieved_at": "2026-11-19T12:00:00+00:00",
        "provider_metadata": {"fixture": "phase2c-runtime-test"},
        "items": [{
            "name": "Fresh Runtime Test Hotel",
            "city": "Goa",
            "total_stay_amount": 14999,
            "currency": "INR",
            "nights": 3,
            "is_free_cancellable": True,
            "is_no_prepayment": True,
        }],
    }


def _make_mission(*, current_artifacts=("hotels",)):
    mission = TravelMission()
    mission.constraints.destination = "Goa"
    mission.constraints.check_in = "2026-12-20"
    mission.constraints.check_out = "2026-12-23"
    mission.constraints.travellers = 2

    first_flight = {
        "price_amount": 6000,
        "currency": "INR",
        "segments": [{
            "origin": "BHO", "destination": "DEL",
            "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00",
        }],
    }
    second_flight = {
        "price_amount": 6200,
        "currency": "INR",
        "segments": [{
            "origin": "BHO", "destination": "DEL",
            "departure": "2026-12-20 12:00", "arrival": "2026-12-20 14:00",
        }],
    }
    mission.candidates["flights"] = [first_flight, second_flight]
    mission.selections["flights"] = {
        "candidate_index": 1,
        "candidate": deepcopy(first_flight),
        "selected_at": "2026-11-19T11:00:00+00:00",
        "selection_status": "selected_not_booked",
    }

    query = {
        "city": "Goa",
        "check_in": "2026-12-20",
        "check_out": "2026-12-23",
        "travellers": 2,
    }
    for artifact in current_artifacts:
        mission.artifacts[artifact] = {
            "status": "current",
            "provider": "previous_fixture",
            "evidence": {
                "tool_name": "search_hotels_stayapi" if artifact == "hotels" else None,
                "query_params": deepcopy(query) if artifact == "hotels" else {},
            },
        }
    if "hotels" in current_artifacts:
        mission.candidates["hotels"] = [{
            "name": "Old Stale Hotel", "city": "Goa",
            "total_stay_amount": 12000, "currency": "INR",
        }]
    return mission


def _create_conversation(db_session, mission):
    user = User(
        email="phase2c-runtime-test@example.invalid",
        name="Phase 2C Runtime Test",
        password_hash="test-only-not-a-real-password-hash",
    )
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(
        user_id=user.id,
        title="Phase 2C runtime verification",
        state_json={MISSION_KEY: mission.model_dump(mode="json")},
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(conversation)
    return user, conversation


def _switch_flight(mission):
    changed = _select_flight_candidate(
        mission, 2, "2026-11-19T12:00:00+00:00"
    )
    assert changed is True
    return mission


def test_runtime_flight_change_stales_only_expected_unconfirmed_dependents():
    dependent = ("hotels", "transfers", "routes", "itinerary", "budget")
    mission = _make_mission(current_artifacts=("flights", *dependent, "hotels_confirmed"))
    mission.artifacts["hotels_confirmed"] = {
        "status": "confirmed", "booking_reference": "USER-CONFIRMED-123"
    }

    _switch_flight(mission)

    assert all(mission.artifacts[name]["status"] == "stale" for name in dependent)
    assert mission.artifacts["flights"]["status"] == "current"
    assert mission.artifacts["hotels_confirmed"]["status"] == "confirmed"
    assert mission.artifacts["hotels_confirmed"]["booking_reference"] == "USER-CONFIRMED-123"
    queued = {
        item["artifact"] for item in mission.pending_recalculations
        if isinstance(item, dict) and item.get("status", "pending") == "pending"
    }
    assert queued == set(dependent)
    assert all(item.get("status") == "pending" for item in mission.pending_recalculations)


def test_runtime_dispatch_executes_safe_search_and_replaces_stale_evidence(db_session):
    mission = _switch_flight(_make_mission(current_artifacts=("hotels",)))
    user, conversation = _create_conversation(db_session, mission)

    def respond(_ctx, _params):
        return ToolResult(True, "Fixture hotel search completed.", _fresh_hotel_payload())

    tool = _FakeHotelSearchTool(respond)
    fake_registry = _FakeRegistry(tool)
    report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=fake_registry
    )

    assert len(tool.calls) == 1
    assert tool.calls[0] == {
        "city": "Goa", "check_in": "2026-12-20",
        "check_out": "2026-12-23", "travellers": 2, "budget": None,
    }
    assert report is not None
    assert report["workflow_id"]
    assert report["executed_steps"]

    state = conversation.state_json
    refreshed = TravelMission.model_validate(state[MISSION_KEY])
    assert refreshed.artifacts["hotels"]["status"] == "current"
    assert refreshed.artifacts["hotels"]["provider"] == "runtime_test_fixture"
    assert refreshed.artifacts["hotels"]["evidence"]["candidate_count"] == 1
    assert refreshed.candidates["hotels"] == [{
        "name": "Fresh Runtime Test Hotel",
        "city": "Goa",
        "total_stay_amount": 14999,
        "currency": "INR",
        "nights": 3,
        "is_free_cancellable": True,
        "is_no_prepayment": True,
    }]
    assert all(
        item.get("artifact") != "hotels"
        for item in refreshed.pending_recalculations
        if isinstance(item, dict)
    )
    stored_feasibility = refreshed.feasibility or {}
    recomputed_feasibility = evaluate_travel_feasibility(
        refreshed.model_dump(mode="json")
    )
    # evaluated_at is intentionally generated per evaluation, so compare the
    # substantive assessment and validate the stored timestamp separately.
    assert stored_feasibility.get("evaluated_at")
    datetime.fromisoformat(stored_feasibility["evaluated_at"].replace("Z", "+00:00"))
    assert {
        key: value for key, value in stored_feasibility.items()
        if key != "evaluated_at"
    } == {
        key: value for key, value in recomputed_feasibility.items()
        if key != "evaluated_at"
    }
    assert state["last_travel_recalculation"]["workflow_id"] == report["workflow_id"]

    workflow = db_session.get(Workflow, report["workflow_id"])
    assert workflow is not None
    hotel_step = next(
        step for step in workflow.steps_json
        if step["tool"] == "search_hotels_stayapi"
    )
    assert hotel_step["status"] == "COMPLETED"
    assert refreshed.selections["flights"]["selection_status"] == "selected_not_booked"


def test_runtime_dispatch_never_invokes_mutating_tool(db_session):
    mission = _switch_flight(_make_mission(current_artifacts=("hotels",)))
    user, conversation = _create_conversation(db_session, mission)

    class MutatingHotelTool(_FakeHotelSearchTool):
        is_mutating = True

    tool = MutatingHotelTool(
        lambda _ctx, _params: ToolResult(True, "Must never execute", _fresh_hotel_payload())
    )
    report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=_FakeRegistry(tool)
    )

    assert tool.calls == []
    assert report is not None
    after = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    pending = next(x for x in after.pending_recalculations if x.get("artifact") == "hotels")
    assert pending["status"] == "blocked"
    assert "mutating" in pending["blocked_reason"].lower()
    assert db_session.query(Workflow).count() == 0


def test_runtime_discards_result_when_mission_version_changes_mid_search(db_session):
    mission = _switch_flight(_make_mission(current_artifacts=("hotels",)))
    user, conversation = _create_conversation(db_session, mission)

    def race_and_respond(_ctx, _params):
        state = dict(conversation.state_json or {})
        raw = dict(state[MISSION_KEY])
        raw["version"] = int(raw["version"]) + 1
        state[MISSION_KEY] = raw
        conversation.state_json = state
        db_session.commit()
        return ToolResult(True, "Late fixture result", _fresh_hotel_payload())

    tool = _FakeHotelSearchTool(race_and_respond)
    report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=_FakeRegistry(tool)
    )

    assert len(tool.calls) == 1
    assert report is not None
    after = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert after.version == mission.version + 1
    assert after.artifacts["hotels"]["status"] == "stale"
    assert after.candidates["hotels"] == [{
        "name": "Old Stale Hotel", "city": "Goa",
        "total_stay_amount": 12000, "currency": "INR",
    }]
    pending = next(x for x in after.pending_recalculations if x.get("artifact") == "hotels")
    assert pending["status"] == "pending"
    assert "mission changed" in pending.get("reason", "").lower() or "mission changed" in pending.get("blocked_reason", "").lower()


class _FakeCabLinkInput(BaseModel):
    pickup_location: str
    dropoff_location: str


class _FakeCabLinkTool(BaseTool):
    name = "get_cab_links"
    description = "Deterministic fake transfer handoff for runtime tests."
    input_schema = _FakeCabLinkInput
    capability = "travel"
    provider_adapters = ()
    requires_confirmation = False
    is_mutating = False

    def __init__(self, callback):
        self.callback = callback
        self.calls = []

    def execute(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        self.calls.append(params.model_dump(mode="json"))
        return self.callback(ctx, params)


def _fresh_transfer_payload():
    return {
        "type": "transport_links",
        "origin": "Airport",
        "destination": "Hotel",
        "links": {"uber": "https://example.invalid/uber", "ola": "https://example.invalid/ola"},
    }


def test_runtime_dispatch_handles_multiple_artifacts_and_successive_runs(db_session):
    mission = _make_mission(current_artifacts=("hotels", "transfers"))
    mission.artifacts["transfers"]["evidence"] = {
        "tool_name": "get_cab_links",
        "query_params": {"pickup_location": "Airport", "dropoff_location": "Hotel"},
    }
    _switch_flight(mission)
    user, conversation = _create_conversation(db_session, mission)

    hotel_tool = _FakeHotelSearchTool(
        lambda _ctx, _params: ToolResult(True, "Fixture hotel search completed.", _fresh_hotel_payload())
    )
    transfer_tool = _FakeCabLinkTool(
        lambda _ctx, _params: ToolResult(True, "Fixture transfer links completed.", _fresh_transfer_payload())
    )
    fake_registry = _FakeRegistry([hotel_tool, transfer_tool])

    first_report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=fake_registry
    )

    assert first_report is not None
    assert len(first_report["executed_steps"]) == 2
    assert len(hotel_tool.calls) == 1
    assert hotel_tool.calls[0]["city"] == "Goa"
    assert len(transfer_tool.calls) == 1
    assert transfer_tool.calls[0] == {
        "pickup_location": "Airport",
        "dropoff_location": "Hotel",
    }

    refreshed = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert refreshed.artifacts["hotels"]["status"] == "current"
    # Cab links are external handoffs, not provider-backed live transfer inventory.
    assert refreshed.artifacts["transfers"]["status"] == "handoff"
    transfer_task = next(
        item for item in refreshed.pending_recalculations
        if isinstance(item, dict) and item.get("artifact") == "transfers"
    )
    assert transfer_task["status"] == "handoff"
    assert transfer_task["result_status"] == "external_handoff"
    assert transfer_task["handoff_links"] == {
        "uber": "https://example.invalid/uber",
        "ola": "https://example.invalid/ola",
    }
    assert not any(
        isinstance(item, dict)
        and item.get("artifact") in {"hotels", "transfers"}
        and item.get("status") in {"pending", "dispatching", "running"}
        for item in refreshed.pending_recalculations
    )

    # A later invalidation should schedule only its new task, not replay the
    # already-completed hotel or transfer work from the previous workflow.
    refreshed.artifacts["hotels"]["status"] = "stale"
    refreshed.pending_recalculations.append({
        "queue_id": "runtime-followup-hotel",
        "artifact": "hotels",
        "tool_name": "search_hotels_stayapi",
        "params": {
            "city": "Goa", "check_in": "2026-12-20",
            "check_out": "2026-12-23", "travellers": 2,
        },
        "status": "pending",
        "reason": "A later constraint change requires another hotel refresh.",
    })
    refreshed.version += 1
    state = dict(conversation.state_json)
    state[MISSION_KEY] = refreshed.model_dump(mode="json")
    conversation.state_json = state
    db_session.commit()

    second_report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=fake_registry
    )

    assert second_report is not None
    assert len(hotel_tool.calls) == 2
    assert len(transfer_tool.calls) == 1
    final_mission = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert not any(
        isinstance(item, dict) and item.get("artifact") == "hotels"
        for item in final_mission.pending_recalculations
    )


def test_runtime_dispatch_suppresses_duplicate_pending_artifact_entries(db_session):
    mission = _switch_flight(_make_mission(current_artifacts=("hotels",)))
    original = next(
        item for item in mission.pending_recalculations
        if isinstance(item, dict) and item.get("artifact") == "hotels"
    )
    duplicate = deepcopy(original)
    duplicate["queue_id"] = "duplicate-hotel-queue-item"
    duplicate["params"] = deepcopy(original.get("params") or {})
    mission.pending_recalculations.append(duplicate)
    user, conversation = _create_conversation(db_session, mission)

    tool = _FakeHotelSearchTool(
        lambda _ctx, _params: ToolResult(True, "Fixture hotel search completed.", _fresh_hotel_payload())
    )
    report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=_FakeRegistry(tool)
    )

    assert report is not None
    assert len(tool.calls) == 1
    after = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert after.artifacts["hotels"]["status"] == "current"
    assert not any(
        isinstance(item, dict) and item.get("artifact") == "hotels"
        for item in after.pending_recalculations
    )


def test_runtime_dispatch_limits_each_run_to_ten_and_resumes_remaining_queue(db_session, monkeypatch):
    import app.services.context.travel_artifacts as artifacts_module
    import app.services.context.travel_recalculation as recalculation_module
    from app.schemas.workflow import WorkflowStep

    mission = _make_mission(current_artifacts=())
    mission.pending_recalculations = [
        {
            "queue_id": f"bounded-queue-{index:02d}",
            "artifact": "hotels",
            "tool_name": "search_hotels_stayapi",
            "params": {
                "city": "Goa", "check_in": "2026-12-20",
                "check_out": "2026-12-23", "travellers": 2,
            },
            "status": "pending",
        }
        for index in range(12)
    ]
    user, conversation = _create_conversation(db_session, mission)

    def prepare_all_pending(raw_mission, _registry):
        pending = [
            item for item in raw_mission.get("pending_recalculations", [])
            if isinstance(item, dict) and item.get("status", "pending") == "pending"
        ]
        steps = [
            WorkflowStep(
                id=f"travel-recalc-{item['queue_id']}",
                description="Bounded dispatcher test step",
                tool="search_hotels_stayapi",
                params=item["params"],
                required=True,
                max_retries=0,
            )
            for item in pending
        ]
        return {"steps": steps, "blocked": [], "local_completed": []}

    # Isolate the dispatcher batch-size contract from evidence semantics: the
    # separate integration tests above exercise the real capture path.
    monkeypatch.setattr(recalculation_module, "prepare_recalculation_steps", prepare_all_pending)
    monkeypatch.setattr(artifacts_module, "capture_workflow_tool_result", lambda **_kwargs: False)

    tool = _FakeHotelSearchTool(
        lambda _ctx, _params: ToolResult(True, "Fixture response.", _fresh_hotel_payload())
    )
    fake_registry = _FakeRegistry(tool)

    first_report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=fake_registry
    )
    assert first_report is not None
    assert len(first_report["executed_steps"]) == 10
    assert len(tool.calls) == 10

    after_first = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    pending_after_first = [
        item for item in after_first.pending_recalculations
        if isinstance(item, dict) and item.get("status") == "pending"
    ]
    assert len(pending_after_first) == 2

    second_report = dispatch_pending_travel_recalculations(
        db_session, user, conversation, registry=fake_registry
    )
    assert second_report is not None
    assert len(second_report["executed_steps"]) == 2
    assert len(tool.calls) == 12

    after_second = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert not any(
        isinstance(item, dict) and item.get("status") == "pending"
        for item in after_second.pending_recalculations
    )
