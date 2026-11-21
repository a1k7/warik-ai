from types import SimpleNamespace

from app.services.context.travel_mission import TravelMission, MISSION_KEY
from app.services.context.travel_artifacts import (
    attach_gmail_booking_evidence,
    confirm_gmail_booking_in_mission,
)


def _conversation():
    mission = TravelMission().model_dump(mode="json")
    return SimpleNamespace(state_json={MISSION_KEY: mission})


def test_gmail_confirmation_candidate_waits_for_user_review():
    conversation = _conversation()
    items = [{
        "message_id": "m-confirm-1",
        "category": "travel",
        "subject": "Your flight booking is confirmed",
        "from": "Airline <noreply@airline.example>",
        "received_at": "2026-11-19T10:00:00Z",
        "snippet": "Your PNR ABC123 and e-ticket are ready.",
    }]
    assert attach_gmail_booking_evidence(conversation, items=items) == 1
    mission = conversation.state_json[MISSION_KEY]
    assert mission["booking_evidence"][0]["status"] == "needs_user_review"
    assert mission["confirmed_bookings"] == []


def test_gmail_partnership_or_application_email_is_not_booking_evidence():
    conversation = _conversation()
    items = [{
        "message_id": "m-false-positive",
        "category": "travel",
        "subject": "Travel partnership application update",
        "from": "Community <hello@example.test>",
        "snippet": "Your application was received. Booking and travel discounts available.",
    }]
    assert attach_gmail_booking_evidence(conversation, items=items) == 0
    assert conversation.state_json[MISSION_KEY]["booking_evidence"] == []
    assert conversation.state_json[MISSION_KEY]["confirmed_bookings"] == []


def test_only_explicit_user_confirmation_promotes_booking_record():
    conversation = _conversation()
    item = {
        "message_id": "m-confirm-2",
        "category": "travel",
        "subject": "Hotel reservation confirmed",
        "from": "Hotel <reservations@hotel.example>",
        "snippet": "Confirmation number ZX123 is your reservation reference.",
    }
    assert attach_gmail_booking_evidence(conversation, items=[item]) == 1
    confirmed = confirm_gmail_booking_in_mission(conversation, message_id="m-confirm-2")
    assert confirmed is not None
    assert confirmed["status"] == "confirmed_by_user"
    assert confirmed["confirmation_method"] == "explicit_user_action"
    mission = conversation.state_json[MISSION_KEY]
    assert len(mission["confirmed_bookings"]) == 1
    assert mission["booking_evidence"][0]["status"] == "user_confirmed"


def test_unknown_gmail_message_cannot_be_confirmed():
    conversation = _conversation()
    assert confirm_gmail_booking_in_mission(conversation, message_id="missing") is None
