"""Opt-in live TRVL CLI hotel workflow smoke test; skipped by default."""
from __future__ import annotations

import os
import shutil
from copy import deepcopy

import pytest

from app.core.config import settings
from app.models import Conversation, User, Workflow
from app.services.context.travel_mission import MISSION_KEY, TravelMission, _select_flight_candidate
from app.services.context.travel_recalculation import dispatch_pending_travel_recalculations
from app.tools.provider_selector import ProviderSelector
from app.tools.registry import registry


pytestmark = pytest.mark.skipif(
    os.getenv("WARIK_RUN_LIVE_TRVL") != "1",
    reason="Set WARIK_RUN_LIVE_TRVL=1 to make one real TRVL CLI hotel search",
)


def _mission_with_one_stale_hotel_search() -> TravelMission:
    mission = TravelMission()
    mission.constraints.destination = "Goa"
    mission.constraints.check_in = "2026-12-20"
    mission.constraints.check_out = "2026-12-23"
    mission.constraints.travellers = 2

    first_flight = {
        "price_amount": 6000, "currency": "INR",
        "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00"}],
    }
    second_flight = {
        "price_amount": 6200, "currency": "INR",
        "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 12:00", "arrival": "2026-12-20 14:00"}],
    }
    mission.candidates["flights"] = [first_flight, second_flight]
    mission.selections["flights"] = {
        "candidate_index": 1, "candidate": deepcopy(first_flight),
        "selected_at": "2026-11-19T11:00:00+00:00",
        "selection_status": "selected_not_booked",
    }
    mission.artifacts["hotels"] = {
        "status": "current", "provider": "previous_fixture",
        "evidence": {
            "tool_name": "search_hotels_stayapi",
            "query_params": {
                "city": "Goa", "check_in": "2026-12-20",
                "check_out": "2026-12-23", "travellers": 2,
            },
        },
    }
    mission.candidates["hotels"] = [{
        "name": "Old Hotel Evidence", "city": "Goa",
        "total_stay_amount": 12000, "currency": "INR",
    }]
    assert _select_flight_candidate(mission, 2, "2026-11-19T12:00:00+00:00")
    return mission


def test_one_real_trvl_cli_hotel_search_runs_through_workflow_and_is_captured(db_session, monkeypatch):
    """One real CLI discovery call; configured API keys are masked in-process only."""
    assert shutil.which("trvl"), "TRVL CLI executable is not installed or not on PATH"

    # WorkflowEngine normally admits authenticated adapters when keys are set.
    # Clear only the in-memory Settings values for this test, forcing trvl_cli.
    # This does not modify .env, shell variables, or saved credentials.
    monkeypatch.setattr(settings, "stayapi_key", "")
    monkeypatch.setattr(settings, "serpapi_api_key", "")

    from app.integrations.stayapi.client import StayAPIClient

    def forbid_stayapi(*_args, **_kwargs):
        raise AssertionError("StayAPI must not be called by a trvl_cli-pinned workflow")

    monkeypatch.setattr(StayAPIClient, "search_hotels", forbid_stayapi)

    tool = registry.get("search_hotels_stayapi")
    assert tool is not None
    selection = ProviderSelector(registry).select(
        capability=tool.capability, operation="search", tool_name=tool.name
    )
    assert selection.available and selection.selected.provider_id == "trvl_cli", selection

    user = User(
        email="phase2c-live-trvl-smoke@example.invalid",
        name="Phase 2C Live TRVL Smoke Test",
        password_hash="test-only-not-a-real-password-hash",
    )
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(
        user_id=user.id,
        title="Opt-in TRVL CLI provider smoke test",
        state_json={MISSION_KEY: _mission_with_one_stale_hotel_search().model_dump(mode="json")},
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(conversation)

    report = dispatch_pending_travel_recalculations(db_session, user, conversation, registry=registry)
    assert report is not None and report.get("workflow_id"), report
    workflow = db_session.get(Workflow, report["workflow_id"])
    assert workflow is not None
    hotel_steps = [step for step in (workflow.steps_json or []) if step.get("tool") == "search_hotels_stayapi"]
    assert len(hotel_steps) == 1, hotel_steps
    step = hotel_steps[0]
    assert step.get("provider_id") == "trvl_cli", step
    assert (step.get("provider_selection") or {}).get("provider_id") == "trvl_cli", step
    assert step.get("status") == "COMPLETED", {
        "workflow_report": report,
        "workflow_status": workflow.status,
        "failed_step": step,
    }

    result_data = step.get("result") or {}
    assert result_data.get("provider") == "trvl_cli", result_data
    assert result_data.get("live_inventory") is True, result_data
    assert isinstance(result_data.get("items"), list), result_data

    mission = TravelMission.model_validate((conversation.state_json or {})[MISSION_KEY])
    artifact = mission.artifacts.get("hotels") or {}
    assert artifact.get("status") == "current", artifact
    assert artifact.get("provider") == "trvl_cli", artifact
    assert artifact.get("evidence", {}).get("live_inventory") is True, artifact
    assert artifact.get("evidence", {}).get("candidate_count") == len(mission.candidates.get("hotels") or []), artifact
    assert not any(isinstance(item, dict) and item.get("artifact") == "hotels" for item in mission.pending_recalculations)
    assert mission.selections["flights"]["selection_status"] == "selected_not_booked"

    print({
        "selected_provider": step.get("provider_id"),
        "result_provider": result_data.get("provider"),
        "live_inventory": result_data.get("live_inventory"),
        "resolution_status": result_data.get("resolution_status"),
        "hotel_candidate_count": len(mission.candidates.get("hotels") or []),
        "artifact_status": artifact.get("status"),
        "workflow_status": workflow.status,
        "booking_created": False,
    })
