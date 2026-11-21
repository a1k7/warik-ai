import asyncio

from app.agents import orchestrator
from app.agents.orchestrator import handle_message
from app.core.security import hash_password
from app.models import Conversation, User


TRAVEL_REQUEST = (
    "Plan my Goa trip for three days under ₹25,000. "
    "Find flights, a hotel and activities."
)


def _user_and_conversation(db, email):
    user = User(
        email=email,
        name="Travel Test",
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    conversation = Conversation(user_id=user.id, title="Goa trip")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return user, conversation


def test_travel_clarification_is_persisted_in_conversation_state(
    db_session, monkeypatch
):
    user, conversation = _user_and_conversation(
        db_session, "pending-travel-initial@example.com"
    )
    monkeypatch.setattr(orchestrator, "get_provider", lambda: object())

    async def ask_for_origin(self, user_message, conversation_context=""):
        assert "Goa" in user_message
        return {
            "decision": "clarification",
            "reply": "I need your departure city first.",
            "plan": None,
        }

    monkeypatch.setattr(
        orchestrator.UniversalTaskPlanner, "interpret", ask_for_origin
    )

    response = asyncio.run(
        handle_message(db_session, user, TRAVEL_REQUEST, conversation)
    )

    assert "departure city" in response.reply.lower()
    assert conversation.state_json["pending_travel"]["original_request"] == TRAVEL_REQUEST
    assert conversation.state_json["pending_travel"]["followups"] == []


def test_departure_city_followup_reenters_original_travel_request(
    db_session, monkeypatch
):
    user, conversation = _user_and_conversation(
        db_session, "pending-travel-followup@example.com"
    )
    conversation.state_json = {
        "pending_travel": {
            "original_request": TRAVEL_REQUEST,
            "followups": [],
        }
    }
    db_session.commit()
    monkeypatch.setattr(orchestrator, "get_provider", lambda: object())
    captured = {}

    async def ask_for_dates(self, user_message, conversation_context=""):
        captured["message"] = user_message
        return {
            "decision": "clarification",
            "reply": "What are your check-in and check-out dates?",
            "plan": None,
        }

    monkeypatch.setattr(
        orchestrator.UniversalTaskPlanner, "interpret", ask_for_dates
    )

    response = asyncio.run(
        handle_message(
            db_session,
            user,
            "Departure city - Delhi",
            conversation,
        )
    )

    assert TRAVEL_REQUEST in captured["message"]
    assert "Departure city - Delhi" in captured["message"]
    assert "check-in" in response.reply.lower()
    assert conversation.state_json["pending_travel"]["followups"] == [
        "Departure city - Delhi"
    ]


def test_unparseable_travel_request_fails_closed_without_llm_synthesis(
    db_session, monkeypatch
):
    user, conversation = _user_and_conversation(
        db_session, "pending-travel-fail-closed@example.com"
    )
    provider = object()
    monkeypatch.setattr(orchestrator, "get_provider", lambda: provider)

    async def planner_failed(self, user_message, conversation_context=""):
        return {
            "decision": "unavailable",
            "reply": None,
            "plan": None,
        }

    monkeypatch.setattr(
        orchestrator.UniversalTaskPlanner, "interpret", planner_failed
    )

    response = asyncio.run(
        handle_message(db_session, user, TRAVEL_REQUEST, conversation)
    )

    assert "couldn't safely build an executable plan" in response.reply.lower()
    assert "no searches or bookings were claimed" in response.reply.lower()
    assert response.structured_data is None
    assert conversation.state_json["pending_travel"]["original_request"] == TRAVEL_REQUEST
