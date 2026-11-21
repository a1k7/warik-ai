from types import SimpleNamespace

from app.services.context.travel_mission import MISSION_KEY, TravelMission
from app.services.context.travel_response import build_travel_mission_read_response


def _conversation(mission=None, state_extra=None):
    state = dict(state_extra or {})
    if mission is not None:
        state[MISSION_KEY] = mission.model_dump(mode="json")
    return SimpleNamespace(state_json=state, messages=[])


def test_booking_status_never_reads_unstructured_conversation_history():
    mission = TravelMission()
    mission.constraints.origin = "Bhopal"
    mission.constraints.destination = "Goa"
    mission.candidates["flights"] = [{"airline": "Test Air", "flight_number": "TA101"}]
    mission.selections["flights"] = {
        "candidate_index": 1,
        "candidate": mission.candidates["flights"][0],
        "selection_status": "selected_not_booked",
    }
    conversation = _conversation(mission)
    conversation.messages = [
        SimpleNamespace(role="assistant", content="Singapore Airlines SQ222 booking 1234567890 confirmed"),
        SimpleNamespace(role="assistant", content="Marina Bay Sands booking 9876543210"),
    ]

    response = build_travel_mission_read_response(
        conversation, "Have you actually booked my flight, hotel or airport transfer?"
    )

    assert response.structured_data["type"] == "travel_mission_read"
    assert response.structured_data["facts"]["warik_booking_action_recorded"] is False
    assert "selected for planning, NOT BOOKED" in response.reply
    assert "Singapore" not in response.reply
    assert "1234567890" not in response.reply
    assert "9876543210" not in response.reply


def test_only_exact_user_reviewed_gmail_candidate_is_reported_confirmed():
    mission = TravelMission()
    mission.booking_evidence = [
        {"message_id": "mail-1", "subject": "Flight booking confirmation", "from": "Airline", "received_at": "2026-11-20", "status": "user_confirmed"},
        {"message_id": "mail-2", "subject": "Hotel booking confirmation", "from": "Booking site", "received_at": "2026-11-20", "status": "needs_user_review"},
    ]
    mission.confirmed_bookings = [{
        "message_id": "mail-1", "subject": "Flight booking confirmation", "from": "Airline",
        "received_at": "2026-11-20", "status": "confirmed_by_user",
        "confirmation_state": "user_confirmed_from_email",
        "confirmation_method": "explicit_user_action",
    }]

    response = build_travel_mission_read_response(
        _conversation(mission), "Show my confirmed bookings and which are still awaiting review."
    )

    facts = response.structured_data["facts"]
    assert [item["message_id"] for item in facts["confirmed_by_user_email_candidates"]] == ["mail-1"]
    assert [item["message_id"] for item in facts["pending_email_candidates"]] == ["mail-2"]
    assert facts["confirmed_by_user_email_candidates"][0]["provider_independently_verified"] is False
    assert "mail-2" not in response.reply.split("User-reviewed Gmail confirmation candidates recorded as confirmed:")[-1].split("still require")[0]


def test_legacy_current_flight_artifact_is_not_presented_as_live_provider_evidence():
    mission = TravelMission()
    mission.artifacts["flights"] = {
        "status": "current",
        "provider": "search_flights_real",
        "source_type": "live_provider_search",
        "retrieved_at": "2026-11-19T14:30:00+00:00",
        "evidence": {"live_inventory": True, "tool_name": "search_flights_real", "candidate_count": 1},
    }
    response = build_travel_mission_read_response(
        _conversation(mission), "Explain where the flight results came from and when they were retrieved."
    )

    flight = response.structured_data["facts"]["flights"]
    assert flight["status"] == "unverified_legacy"
    assert flight["provider"] is None
    assert flight["retrieved_at"] is None
    assert "not independently attributable" in response.reply
    assert "not recorded/verified" in response.reply


def test_explicit_live_provider_and_timestamp_flags_allow_provenance_display():
    mission = TravelMission()
    mission.artifacts["flights"] = {
        "status": "current",
        "provider": "serpapi_google_flights",
        "source_type": "live_provider_search",
        "retrieved_at": "2026-11-20T09:00:00+00:00",
        "evidence": {
            "live_inventory": True,
            "provider_attribution_verified": True,
            "provider_retrieval_timestamp_verified": True,
            "candidate_count": 2,
        },
    }
    response = build_travel_mission_read_response(
        _conversation(mission), "Show actual provider attribution and retrieval times."
    )
    flight = response.structured_data["facts"]["flights"]
    assert flight["provider"] == "serpapi_google_flights"
    assert flight["retrieved_at"] == "2026-11-20T09:00:00+00:00"
    assert "serpapi_google_flights" in response.reply


def test_queue_distinguishes_deferred_from_completed():
    mission = TravelMission()
    mission.pending_recalculations = [{
        "queue_id": "queue-1", "artifact": "hotels", "status": "pending",
        "reason": "An existing workflow is active.",
    }]
    response = build_travel_mission_read_response(
        _conversation(mission, {"last_travel_recalculation": {"status": "deferred", "reason": "Another workflow is active"}}),
        "Show me the current travel recalculation queue, including completed, pending and deferred tasks.",
    )
    facts = response.structured_data["facts"]
    assert facts["deferred"][0]["queue_id"] == "queue-1"
    assert facts["completed_evidence_artifacts"] == []
    assert "not evidence that a provider search completed" in response.reply


def test_audit_does_not_claim_an_empty_mission_is_feasible_or_booked():
    response = build_travel_mission_read_response(
        _conversation(TravelMission()), "Perform a complete audit of my current Goa travel mission."
    )
    assert response.structured_data["intent"] == "audit"
    assert "Booking ledger" in response.reply
    assert "No user-confirmed booking evidence" in response.reply
    assert "UNKNOWN" in response.reply
    assert "PASS: All constraints and preferences met" not in response.reply


def test_gmail_discovery_is_not_intercepted_as_a_local_ledger_read():
    mission = TravelMission()
    response = build_travel_mission_read_response(
        _conversation(mission),
        "Check my connected Gmail account for flight, hotel or travel booking confirmation messages.",
    )
    assert response is None


def test_read_request_without_saved_mission_does_not_fall_back_to_chat_history():
    conversation = _conversation(None)
    conversation.messages = [SimpleNamespace(role="assistant", content="You booked three hotels in Singapore.")]
    response = build_travel_mission_read_response(
        conversation, "Have you booked my hotel?"
    )
    assert response.structured_data["mission_available"] is False
    assert "cannot verify" in response.reply
    assert "Singapore" not in response.reply


def test_tool_result_without_provider_or_timestamp_is_not_fresh_evidence():
    from app.services.context.travel_artifacts import attach_tool_result_to_mission

    mission = TravelMission()
    conversation = _conversation(mission)
    attached = attach_tool_result_to_mission(
        conversation,
        tool_name="search_flights_real",
        params={"origin": "Bhopal", "destination": "Goa", "date": "2026-12-20"},
        result_data={
            "type": "flight_list",
            "live_inventory": True,
            "items": [{"airline": "Unattributed Air", "flight_number": "UA100"}],
        },
    )

    artifact = conversation.state_json[MISSION_KEY]["artifacts"]["flights"]
    assert attached is False
    assert artifact["status"] == "unverified"
    assert artifact["provider"] is None
    assert artifact["retrieved_at"] is None
    assert artifact["captured_at"]


def test_external_transfer_handoff_is_not_current_quote_or_booking_evidence():
    from app.services.context.travel_artifacts import attach_tool_result_to_mission

    conversation = _conversation(TravelMission())
    attached = attach_tool_result_to_mission(
        conversation,
        tool_name="get_cab_links",
        params={"pickup_location": "GOI", "dropoff_location": "Hotel"},
        result_data={
            "type": "transport_links",
            "origin": "Goa Airport",
            "destination": "Hotel",
            "links": {"uber": "https://m.uber.com/ul/"},
        },
    )
    artifact = conversation.state_json[MISSION_KEY]["artifacts"]["transfers"]
    assert attached is False
    assert artifact["status"] == "handoff"
    assert artifact["source_type"] == "external_handoff"
    assert artifact["retrieved_at"] is None


def test_completed_workflow_cleanup_preserves_travel_mission(db_session):
    import asyncio
    from types import SimpleNamespace
    from app.agents.orchestrator import _workflow_response
    from app.models import User, Conversation

    user = User(
        email="travel-state-preserve@example.invalid",
        name="Travel State Test",
        password_hash="test-only-not-a-real-password-hash",
    )
    db_session.add(user)
    db_session.flush()
    mission = TravelMission()
    mission.constraints.destination = "Goa"
    conversation = Conversation(
        user_id=user.id,
        title="State preservation test",
        state_json={
            MISSION_KEY: mission.model_dump(mode="json"),
            "active_workflow_id": 777,
            "conversation_context": {"latest_user_message": "Plan Goa"},
        },
    )
    db_session.add(conversation)
    db_session.commit()

    workflow = SimpleNamespace(
        id=777,
        status="COMPLETED",
        steps_json=[{
            "id": "summary",
            "description": "Compile trip summary",
            "tool": "compile_trip_summary",
            "status": "COMPLETED",
            "result": {"type": "trip_summary", "destination": "Goa"},
        }],
    )
    response = asyncio.run(_workflow_response(
        db_session, user, conversation, workflow, {"workflow_status": "COMPLETED"}
    ))

    assert response.structured_data["destination"] == "Goa"
    assert MISSION_KEY in conversation.state_json
    saved = TravelMission.model_validate(conversation.state_json[MISSION_KEY])
    assert saved.constraints.destination == "Goa"
    assert "active_workflow_id" not in conversation.state_json
    assert conversation.state_json["conversation_context"]["latest_user_message"] == "Plan Goa"



def test_selected_recommended_and_handoff_options_are_separated():
    mission = TravelMission()
    mission.candidates["flights"] = [
        {"airline": "Example Air", "flight_number": "EX101"},
        {"airline": "Example Air", "flight_number": "EX202"},
    ]
    mission.selections["flights"] = {
        "candidate_index": 2,
        "candidate": mission.candidates["flights"][1],
        "selection_status": "selected_not_booked",
    }
    mission.candidates["transfers"] = [{
        "kind": "external_handoff",
        "links": {"uber": "https://example.invalid/uber"},
    }]
    mission.artifacts["transfers"] = {"status": "handoff", "source_type": "external_handoff"}

    response = build_travel_mission_read_response(
        _conversation(mission),
        "Show me which options are selected, which are recommendations and which are external handoffs.",
    )

    assert response.structured_data["intent"] == "options"
    options = response.structured_data["facts"]["options"]["flights"]
    assert options[0]["status"] == "recommendation_only"
    assert options[1]["status"] == "selected_not_booked"
    assert response.structured_data["facts"]["external_handoffs"][0]["validated"] is False
    assert "SELECTED — NOT BOOKED" in response.reply
    assert "recommendation only" in response.reply
    assert "not booked" in response.reply.lower()


def test_booking_queries_in_question_form_are_deterministic_reads():
    from app.services.context.travel_response import _intent_for

    assert _intent_for("Is my hotel booked?") == "bookings"
    assert _intent_for("Are my flight and transfer reservations confirmed?") == "bookings"
    assert _intent_for("Which bookings have independent confirmation evidence?") == "bookings"
