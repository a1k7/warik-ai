from datetime import date
from types import SimpleNamespace

from app.services.context.travel_mission import (
    format_travel_mission_context,
    mark_travel_artifact_current,
    update_travel_mission,
)
from app.services.context.conversation_context import (
    build_conversation_context,
    update_conversation_context,
)


def _conversation():
    return SimpleNamespace(state_json={}, messages=[])


def test_creates_mission_from_explicit_trip_request():
    conversation = _conversation()
    mission = update_travel_mission(
        conversation,
        "Plan a 5-day trip from Bhopal to Goa for 2 people under ₹35,000",
        reference_date=date(2026, 11, 19),
    )
    assert mission is not None
    assert mission["constraints"]["origin"] == "Bhopal"
    assert mission["constraints"]["destination"] == "Goa"
    assert mission["constraints"]["trip_days"] == 5
    assert mission["constraints"]["travellers"] == 2
    assert mission["constraints"]["budget_amount"] == 35000
    assert mission["constraints"]["budget_currency"] == "INR"


def test_unrelated_message_does_not_create_travel_mission():
    conversation = _conversation()
    update_conversation_context(conversation, "Help me write a Java assignment")
    assert "travel_mission" not in conversation.state_json


def test_follow_up_preserves_previous_slots_and_updates_budget():
    conversation = _conversation()
    update_travel_mission(
        conversation,
        "Plan a trip from Bhopal to Goa for 2 people",
        reference_date=date(2026, 11, 19),
    )
    updated = update_travel_mission(conversation, "Make it cheaper, budget ₹30,000")
    assert updated["constraints"]["origin"] == "Bhopal"
    assert updated["constraints"]["destination"] == "Goa"
    assert updated["constraints"]["travellers"] == 2
    assert updated["constraints"]["budget_amount"] == 30000


def test_changing_destination_invalidates_current_dependent_artifacts():
    conversation = _conversation()
    mission = update_travel_mission(
        conversation,
        "Trip from Bhopal to Goa for 2 people",
        reference_date=date(2026, 11, 19),
    )
    mission["artifacts"]["flights"] = {"status": "current", "provider": "test"}
    mission["artifacts"]["hotels"] = {"status": "current", "provider": "test"}
    mission["artifacts"]["transfers"] = {"status": "current", "provider": "test"}
    mission["artifacts"]["itinerary"] = {"status": "current", "provider": "test"}
    conversation.state_json["travel_mission"] = mission

    updated = update_travel_mission(conversation, "Change the destination to Mumbai")
    assert updated["constraints"]["destination"] == "Mumbai"
    for key in ("flights", "hotels", "transfers", "itinerary"):
        assert updated["artifacts"][key]["status"] == "stale"


def test_mark_artifact_records_provenance_and_not_booking_status():
    conversation = _conversation()
    mission = update_travel_mission(
        conversation,
        "Find flights from Bhopal to Delhi",
        reference_date=date(2026, 11, 19),
    )
    updated = mark_travel_artifact_current(
        mission,
        "flights",
        provider="serpapi_google_flights",
        source_type="live_search",
        retrieved_at="2026-11-19T12:00:00+00:00",
        evidence={"result_count": 3},
    )
    assert updated["artifacts"]["flights"]["status"] == "current"
    assert updated["artifacts"]["flights"]["provider"] == "serpapi_google_flights"
    assert updated["artifacts"]["flights"]["source_type"] == "live_search"
    assert "booking_status" not in updated["artifacts"]["flights"]


def test_mission_is_included_in_bounded_planner_context():
    conversation = _conversation()
    update_conversation_context(
        conversation,
        "Plan a trip from Bhopal to Goa for 2 people under ₹35,000",
    )
    text = build_conversation_context(conversation, latest_text="Find flights")
    assert "ACTIVE TRAVEL MISSION" in text
    assert '"origin":"Bhopal"' in text
    assert "stale results" in text


def test_artifact_context_formatter_handles_bad_state_safely():
    assert format_travel_mission_context({"not": "a valid mission"}) == ""
