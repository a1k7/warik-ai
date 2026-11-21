from app.services.context.travel_feasibility import evaluate_travel_feasibility


def _mission():
    return {
        "version": 3,
        "constraints": {"departure_date": "2026-12-20", "check_in": "2026-12-20", "budget_amount": 30000, "budget_currency": "INR"},
        "preferences": {},
        "candidates": {},
        "artifacts": {
            "flights": {"status": "current"},
            "hotels": {"status": "current"},
            "routes": {"status": "current", "source_type": "straight_line_estimate", "evidence": {"road_distance_km": None, "travel_duration_minutes": None}},
        },
        "selections": {
            "flights": {"candidate": {"price_amount": 8000, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 07:00", "arrival": "2026-12-20 09:00"}]}},
            "hotels": {"candidate": {"total_stay_amount": 12000, "currency": "INR", "check_in": "2026-12-20"}},
        },
        "pending_recalculations": [],
    }


def _check(report, name):
    return next(item for item in report["checks"] if item["id"] == name)


def test_known_selected_costs_are_summed_but_incomplete_trip_is_unknown():
    report = evaluate_travel_feasibility(_mission())
    assert report["known_subtotal"] == 20000
    assert report["known_subtotal_currency"] == "INR"
    assert _check(report, "budget")["status"] == "UNKNOWN"
    assert "food" in report["missing_cost_components"]


def test_known_selected_costs_over_budget_fail_even_if_other_costs_are_unknown():
    mission = _mission()
    mission["constraints"]["budget_amount"] = 15000
    report = evaluate_travel_feasibility(mission)
    assert _check(report, "budget")["status"] == "FAIL"


def test_currency_mismatch_is_unknown_not_converted():
    mission = _mission()
    mission["selections"]["hotels"]["candidate"]["currency"] = "USD"
    report = evaluate_travel_feasibility(mission)
    assert _check(report, "budget")["status"] == "UNKNOWN"
    assert report["known_subtotal"] is None


def test_arrival_after_hotel_checkin_is_a_schedule_failure():
    mission = _mission()
    mission["selections"]["flights"]["candidate"]["segments"][0]["arrival"] = "2026-12-21 01:00"
    report = evaluate_travel_feasibility(mission)
    assert _check(report, "arrival_before_hotel_checkin")["status"] == "FAIL"


def test_straight_line_route_does_not_claim_duration():
    report = evaluate_travel_feasibility(_mission())
    route = _check(report, "route_timing")
    assert route["status"] == "UNKNOWN"
    assert route["travel_duration_minutes"] is None


def test_stale_flight_selection_is_not_used_for_costs():
    mission = _mission()
    mission["artifacts"]["flights"]["status"] = "stale"
    report = evaluate_travel_feasibility(mission)
    assert report["known_subtotal"] is None
    assert _check(report, "selected_flight")["status"] == "UNKNOWN"


def test_pending_recalculations_are_visible_as_warning():
    mission = _mission()
    mission["pending_recalculations"] = [{"artifact": "hotels", "status": "pending"}]
    report = evaluate_travel_feasibility(mission)
    assert _check(report, "dependent_artifacts")["status"] == "WARNING"
    assert report["status"] in {"WARNING", "UNKNOWN"}


def test_flight_selection_uses_nested_segments_to_detect_schedule_changes():
    from app.services.context.travel_mission import TravelMission, _select_flight_candidate

    mission = TravelMission()
    first = {"price_amount": 8000, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 07:00", "arrival": "2026-12-20 09:00"}]}
    second = {"price_amount": 8200, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 07:00", "arrival": "2026-12-20 11:00"}]}
    mission.candidates["flights"] = [first, second]
    mission.artifacts["flights"] = {"status": "current"}
    mission.artifacts["hotels"] = {"status": "current", "evidence": {"tool_name": "search_hotels_stayapi", "query_params": {"city": "Delhi"}}}
    mission.artifacts["transfers"] = {"status": "current", "evidence": {"tool_name": "get_cab_links", "query_params": {"pickup_location": "DEL Airport"}}}
    mission.artifacts["routes"] = {"status": "current", "evidence": {"tool_name": "optimize_route", "query_params": {"places": []}}}
    mission.artifacts["itinerary"] = {"status": "current", "evidence": {"tool_name": "generate_advanced_itinerary", "query_params": {"destination": "Delhi"}}}
    mission.artifacts["budget"] = {"status": "current", "evidence": {"tool_name": "calculate_trip_budget", "query_params": {"total_budget": 30000}}}

    # First selection establishes the baseline; no prior schedule can be compared.
    assert _select_flight_candidate(mission, 1, "2026-11-19T00:00:00+00:00")
    assert all(mission.artifacts[name]["status"] == "current" for name in ("hotels", "transfers", "routes", "itinerary", "budget"))
    assert mission.pending_recalculations == []

    # A later flight with a different arrival time invalidates dependent results.
    assert _select_flight_candidate(mission, 2, "2026-11-19T00:01:00+00:00")
    assert all(mission.artifacts[name]["status"] == "stale" for name in ("hotels", "transfers", "routes", "itinerary", "budget"))
    assert {item["artifact"] for item in mission.pending_recalculations} == {"hotels", "transfers", "routes", "itinerary", "budget"}



def test_flight_selection_preserves_confirmed_booking_artifact():
    from app.services.context.travel_mission import TravelMission, _select_flight_candidate

    mission = TravelMission()
    mission.candidates["flights"] = [{"price_amount": 8000, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 07:00", "arrival": "2026-12-20 09:00"}]}]
    mission.artifacts["flights"] = {"status": "current"}
    mission.artifacts["hotels"] = {"status": "current", "booking_status": "confirmed", "evidence": {"tool_name": "search_hotels_stayapi"}}
    _select_flight_candidate(mission, 1, "2026-11-19T00:00:00+00:00")
    assert mission.artifacts["hotels"]["status"] == "current"
    assert not any(item["artifact"] == "hotels" for item in mission.pending_recalculations)


def test_choose_hotel_followup_is_processed_and_affects_budget_and_transfers():
    from types import SimpleNamespace
    from app.services.context.travel_mission import TravelMission, update_travel_mission

    mission = TravelMission()
    mission.candidates["hotels"] = [
        {"name": "Hotel A", "total_stay_amount": 9000, "currency": "INR", "check_in": "2026-12-20"},
        {"name": "Hotel B", "total_stay_amount": 12000, "currency": "INR", "check_in": "2026-12-20"},
    ]
    mission.artifacts["hotels"] = {"status": "current"}
    mission.artifacts["budget"] = {"status": "current", "evidence": {"tool_name": "calculate_trip_budget", "query_params": {"total_budget": 30000}}}
    mission.artifacts["transfers"] = {"status": "current", "evidence": {"tool_name": "get_cab_links", "query_params": {}}}
    conversation = SimpleNamespace(state_json={"travel_mission": mission.model_dump(mode="json")})
    result = update_travel_mission(conversation, "choose hotel 2")
    assert result["selections"]["hotels"]["candidate"]["name"] == "Hotel B"
    assert result["selections"]["hotels"]["selection_status"] == "selected_not_booked"
    assert result["artifacts"]["budget"]["status"] == "stale"
    assert result["artifacts"]["transfers"]["status"] == "stale"


def test_choose_flight_followup_is_processed_and_feasibility_persisted():
    from types import SimpleNamespace
    from app.services.context.travel_mission import TravelMission, update_travel_mission

    mission = TravelMission()
    mission.candidates["flights"] = [{"price_amount": 8000, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 07:00", "arrival": "2026-12-20 09:00"}]}]
    mission.artifacts["flights"] = {"status": "current"}
    conversation = SimpleNamespace(state_json={"travel_mission": mission.model_dump(mode="json")})
    result = update_travel_mission(conversation, "choose flight 1")
    assert result["selections"]["flights"]["selection_status"] == "selected_not_booked"
    assert result["feasibility"]["status"] in {"UNKNOWN", "WARNING", "FAIL", "PASS"}
