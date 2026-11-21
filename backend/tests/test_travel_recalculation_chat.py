"""Chat-level integration tests for travel recalculation acknowledgement."""
from __future__ import annotations

import asyncio
from copy import deepcopy

from pydantic import BaseModel

from app.agents import orchestrator
from app.agents.orchestrator import handle_message
from app.models import Conversation, User, Workflow
from app.services.context.travel_mission import MISSION_KEY, TravelMission
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.tools.travel_apis import HotelInput


class _ChatHotelTool(BaseTool):
    name = "search_hotels_stayapi"
    description = "Test-only hotel discovery tool."
    input_schema = HotelInput
    capability = "travel"
    provider_adapters = ()
    is_mutating = False
    requires_confirmation = False

    def __init__(self):
        self.calls = []

    def execute(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        self.calls.append(params.model_dump(mode="json"))
        return ToolResult(True, "Fixture hotel search completed.", {
            "type": "hotel_list",
            "provider": "chat_runtime_fixture",
            "live_inventory": True,
            "retrieved_at": "2026-11-19T18:00:00+00:00",
            "items": [{
                "name": "Fresh Chat Test Hotel",
                "city": "Goa",
                "total_stay_amount": 15800,
                "currency": "INR",
                "nights": 3,
            }],
        })


class _ChatRegistry:
    def __init__(self, tool):
        self.tool = tool

    def get(self, name):
        return self.tool if name == self.tool.name else None

    def list_tools(self):
        return [self.tool.name]

    def dispatch(self, context, name, params, provider_id=None):
        tool = self.get(name)
        if tool is None:
            return ToolResult(False, f"Unknown test tool: {name}", {})
        validated = tool.input_schema(**params)
        return tool.execute(context, validated)


def _mission_with_stale_hotel(*, include_travellers=True):
    mission = TravelMission()
    mission.constraints.destination = "Goa"
    mission.constraints.check_in = "2026-12-20"
    mission.constraints.check_out = "2026-12-23"
    if include_travellers:
        mission.constraints.travellers = 2

    first = {
        "price_amount": 6000, "currency": "INR",
        "segments": [{
            "origin": "BHO", "destination": "DEL",
            "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00",
        }],
    }
    second = {
        "price_amount": 6200, "currency": "INR",
        "segments": [{
            "origin": "BHO", "destination": "DEL",
            "departure": "2026-12-20 12:00", "arrival": "2026-12-20 14:00",
        }],
    }
    mission.candidates["flights"] = [first, second]
    mission.selections["flights"] = {
        "candidate_index": 1, "candidate": deepcopy(first),
        "selected_at": "2026-11-19T17:00:00+00:00",
        "selection_status": "selected_not_booked",
    }
    old_query = {
        "city": "Goa", "check_in": "2026-12-20", "check_out": "2026-12-23",
    }
    if include_travellers:
        old_query["travellers"] = 2
    mission.artifacts["hotels"] = {
        "status": "current", "provider": "previous_fixture",
        "evidence": {
            "tool_name": "search_hotels_stayapi",
            "query_params": old_query,
        },
    }
    mission.candidates["hotels"] = [{
        "name": "Old Chat Test Hotel", "city": "Goa",
        "total_stay_amount": 12000, "currency": "INR",
    }]
    return mission


def _create_user_conversation(db_session, mission):
    user = User(
        email="travel-recalc-chat@example.invalid",
        name="Travel Chat Test",
        password_hash="test-only-not-a-real-password-hash",
    )
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(
        user_id=user.id,
        title="Travel recalculation chat test",
        state_json={MISSION_KEY: mission.model_dump(mode="json")},
    )
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(conversation)
    return user, conversation


def test_chat_flight_selection_runs_refresh_and_returns_fresh_results(db_session, monkeypatch):
    mission = _mission_with_stale_hotel()
    user, conversation = _create_user_conversation(db_session, mission)
    tool = _ChatHotelTool()
    monkeypatch.setattr(orchestrator, "registry", _ChatRegistry(tool))

    response = asyncio.run(handle_message(
        db_session, user, "choose flight option 2", conversation
    ))

    assert len(tool.calls) == 1
    assert tool.calls[0]["city"] == "Goa"
    assert response.structured_data["type"] == "travel_recalculation"
    assert response.structured_data["refreshed_artifacts"] == ["hotels"]
    assert response.structured_data["booking_status"] == "not_booked"
    assert "refreshed the hotel search" in response.reply.lower()
    assert "not been booked" in response.reply.lower()

    after = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert after.artifacts["hotels"]["status"] == "current"
    assert after.candidates["hotels"][0]["name"] == "Fresh Chat Test Hotel"
    assert not any(x.get("artifact") == "hotels" for x in after.pending_recalculations)
    workflow = db_session.query(Workflow).filter(Workflow.user_id == user.id).one()
    assert workflow.status == "COMPLETED"


def test_chat_incomplete_refresh_explains_missing_traveller_count(db_session, monkeypatch):
    mission = _mission_with_stale_hotel(include_travellers=False)
    user, conversation = _create_user_conversation(db_session, mission)
    tool = _ChatHotelTool()
    monkeypatch.setattr(orchestrator, "registry", _ChatRegistry(tool))

    response = asyncio.run(handle_message(
        db_session, user, "choose flight option 2", conversation
    ))

    assert tool.calls == []
    assert response.structured_data["type"] == "travel_recalculation"
    blocked = response.structured_data["blocked_artifacts"]
    assert blocked and blocked[0]["artifact"] == "hotels"
    assert "traveller count" in blocked[0]["reason"].lower()
    assert "not been booked" in response.reply.lower()
    assert db_session.query(Workflow).filter(Workflow.user_id == user.id).count() == 0


def test_chat_reports_deferred_refresh_as_pending_not_completed(db_session, monkeypatch):
    mission = _mission_with_stale_hotel()
    user, conversation = _create_user_conversation(db_session, mission)
    tool = _ChatHotelTool()
    monkeypatch.setattr(orchestrator, "registry", _ChatRegistry(tool))

    # Create a real active workflow row so the dispatcher must defer.
    from app.models.workflow import Goal
    goal = Goal(
        user_id=user.id, conversation_id=conversation.id,
        title="Existing user workflow", status="EXECUTING", context_json={},
    )
    db_session.add(goal)
    db_session.flush()
    active = Workflow(
        user_id=user.id, goal_id=goal.id, status="IN_PROGRESS", steps_json=[],
    )
    db_session.add(active)
    db_session.flush()
    state = dict(conversation.state_json or {})
    state["active_workflow_id"] = active.id
    conversation.state_json = state
    db_session.commit()

    response = asyncio.run(handle_message(
        db_session, user, "choose flight option 2", conversation
    ))

    assert tool.calls == []
    assert response.structured_data["status"] == "deferred"
    assert response.structured_data["pending_artifacts"] == ["hotels"]
    assert "still pending" in response.reply.lower()
    assert "refreshed the hotel search" not in response.reply.lower()
    assert "not been booked" in response.reply.lower()
