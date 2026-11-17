from types import SimpleNamespace

from app.services.context.conversation_context import (
    build_conversation_context, extract_task_entities, is_resume_request,
    update_conversation_context,
)


def test_entity_extraction_keeps_only_literal_mentions():
    result = extract_task_entities("Plan a trip to Tokyo for 5 days under ₹45,000 from 12 Nov 2026")
    assert result["location_mention"] == "Tokyo"
    assert result["budget_mention"] == 45000
    assert result["date_mentions"] == ["12 Nov 2026"]


def test_update_merges_state_without_erasing_existing_slots():
    conversation = SimpleNamespace(state_json={"last_location": "Paris", "awaiting": {"slot": "dates"}})
    state = update_conversation_context(conversation, "Make it cheaper")
    assert state["last_location"] == "Paris"
    assert state["awaiting"] == {"slot": "dates"}
    assert state["conversation_context"]["latest_user_message"] == "Make it cheaper"


def test_context_includes_recent_turns_and_active_workflow_bounded():
    conversation = SimpleNamespace(
        state_json={"conversation_context": {"latest_user_message": "Plan Tokyo", "entities": {"location_mention": "Tokyo"}}},
        messages=[SimpleNamespace(role="user", content="Plan Tokyo"), SimpleNamespace(role="assistant", content="How many days?")],
    )
    workflow = SimpleNamespace(id=7, status="IN_PROGRESS", steps_json=[{"id": "s1", "description": "Find attractions", "status": "COMPLETED", "tool": "discover_places"}])
    result = build_conversation_context(conversation, "Make it cheaper", workflow)
    assert "Plan Tokyo" in result
    assert "Make it cheaper" in result
    assert "COMPLETED" in result
    assert len(result) <= 8000


def test_resume_requires_explicit_unambiguous_command():
    assert is_resume_request("continue")
    assert is_resume_request("Please proceed with remaining steps")
    assert not is_resume_request("continue but make it cheaper")
    assert not is_resume_request("yes")


def test_latest_user_message_is_included_once_when_already_persisted():
    current = "I'll send Rahul the project report by Friday."
    conversation = SimpleNamespace(
        state_json={"conversation_context": {"latest_user_message": current}},
        messages=[SimpleNamespace(role="user", content=current)],
    )
    result = build_conversation_context(conversation, current)
    assert result.count(current) == 1
    assert "Previous task request:" not in result


def test_previous_request_is_not_duplicated_in_recent_history():
    conversation = SimpleNamespace(
        state_json={"conversation_context": {"latest_user_message": "Plan Tokyo"}},
        messages=[
            SimpleNamespace(role="user", content="Plan Tokyo"),
            SimpleNamespace(role="assistant", content="How many days?"),
            SimpleNamespace(role="user", content="Make it cheaper"),
        ],
    )
    result = build_conversation_context(conversation, "Make it cheaper")
    assert result.count("Plan Tokyo") == 1
    assert result.count("Make it cheaper") == 1



def test_context_carries_bounded_flight_options_for_follow_up():
    flight_result = {
        "type": "flight_list",
        "live_inventory": True,
        "filters_applied": {"departure_time_from": "18:00"},
        "items": [
            {
                "price": "₹5,200",
                "currency": "INR",
                "departure_time": "2026-12-20 19:10",
                "arrival_time": "2026-12-20 21:00",
                "stops": 0,
                "url": "https://example.test/flight/offer-1",
                "segments": [{
                    "airline": "Example Air",
                    "flight_number": "EX101",
                    "origin": "BOM",
                    "destination": "DEL",
                    "departure": "2026-12-20 19:10",
                    "arrival": "2026-12-20 21:00",
                }],
                "provider_private_payload": {"token": "must-not-copy"},
            }
        ],
    }
    conversation = SimpleNamespace(
        state_json={},
        messages=[
            SimpleNamespace(role="user", content="Find evening flights."),
            SimpleNamespace(role="assistant", content="I found flight options.", structured_data=flight_result),
            SimpleNamespace(role="user", content="Use the cheaper one and find a cab."),
        ],
    )

    result = build_conversation_context(conversation, "Use the cheaper one and find a cab.")

    assert "Previous travel options" in result
    assert "2026-12-20 19:10" in result
    assert "offer-1" in result
    assert "must-not-copy" not in result
