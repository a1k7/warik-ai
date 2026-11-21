from types import SimpleNamespace

from app.services.context.travel_artifacts import attach_tool_result_to_mission
from app.services.context.travel_mission import (
    MISSION_KEY,
    TravelMission,
    _select_flight_candidate,
)


def _conversation_with_mission():
    mission = TravelMission()
    return SimpleNamespace(state_json={MISSION_KEY: mission.model_dump(mode="json")})


def test_flight_result_attaches_candidates_segments_and_provenance():
    conversation = _conversation_with_mission()
    attached = attach_tool_result_to_mission(
        conversation,
        tool_name="search_flights_real",
        params={"origin": "Bhopal", "destination": "Delhi"},
        selected_provider_id="serpapi_google_flights",
        result_data={
            "type": "flight_list",
            "provider": "serpapi_google_flights",
            "live_inventory": True,
            "retrieved_at": "2026-11-19T10:00:00+00:00",
            "provider_metadata": {"search_id": "safe-id"},
            "items": [{
                "price": "₹6,000",
                "price_amount": 6000,
                "currency": "INR",
                "segments": [{
                    "origin": "BHO",
                    "destination": "DEL",
                    "departure": "2026-12-20 08:00",
                    "arrival": "2026-12-20 10:00",
                }],
            }],
        },
    )
    assert attached is True
    mission = conversation.state_json[MISSION_KEY]
    assert mission["candidates"]["flights"][0]["segments"][0]["origin"] == "BHO"
    artifact = mission["artifacts"]["flights"]
    assert artifact["provider"] == "serpapi_google_flights"
    assert artifact["source_type"] == "live_provider_search"
    assert artifact["retrieved_at"] == "2026-11-19T10:00:00+00:00"
    assert artifact["mission_version"] == mission["version"]
    assert artifact["constraints_fingerprint"]


def test_hotel_result_preserves_total_price_currency_and_cancellation_terms():
    conversation = _conversation_with_mission()
    attach_tool_result_to_mission(
        conversation,
        tool_name="search_hotels_stayapi",
        params={"city": "Goa", "check_in": "2026-12-20", "check_out": "2026-12-23"},
        result_data={
            "type": "hotel_list",
            "provider": "stayapi_booking",
            "live_inventory": True,
            "items": [{
                "name": "Test Hotel",
                "total_stay_amount": 15000,
                "currency": "INR",
                "is_free_cancellable": True,
                "is_no_prepayment": False,
                "nights": 3,
            }],
        },
    )
    item = conversation.state_json[MISSION_KEY]["candidates"]["hotels"][0]
    assert item["total_stay_amount"] == 15000
    assert item["currency"] == "INR"
    assert item["is_free_cancellable"] is True
    assert item["is_no_prepayment"] is False
    evidence = conversation.state_json[MISSION_KEY]["artifacts"]["hotels"]["evidence"]
    assert evidence["total_stay_quotes"] == 1
    assert set(evidence["cancellation_fields"]) == {"is_free_cancellable", "is_no_prepayment"}


def test_handoff_links_are_never_classified_as_live_route_quotes():
    conversation = _conversation_with_mission()
    attach_tool_result_to_mission(
        conversation,
        tool_name="get_cab_links",
        params={"pickup_location": "Airport", "dropoff_location": "Hotel"},
        result_data={
            "type": "transport_links",
            "origin": "Airport",
            "destination": "Hotel",
            "links": {"uber": "https://m.uber.com/ul/"},
        },
    )
    artifact = conversation.state_json[MISSION_KEY]["artifacts"]["transfers"]
    assert artifact["source_type"] == "external_handoff"
    assert artifact["status"] == "handoff"
    assert artifact["retrieved_at"] is None
    assert conversation.state_json[MISSION_KEY]["candidates"]["transfers"][0]["kind"] == "external_handoff"


def test_changing_selected_flight_stales_dependents_but_keeps_confirmed_booking():
    mission = TravelMission()
    mission.candidates["flights"] = [
        {
            "price_amount": 6000,
            "currency": "INR",
            "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00"}],
        },
        {
            "price_amount": 6200,
            "currency": "INR",
            "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 12:00", "arrival": "2026-12-20 14:00"}],
        },
    ]
    for name in ("flights", "hotels", "transfers", "routes", "itinerary", "budget"):
        mission.artifacts[name] = {"status": "current"}
    mission.artifacts["hotels_confirmed"] = {"status": "confirmed", "booking_reference": "USER-REF"}

    assert _select_flight_candidate(mission, 1, "2026-11-19T10:00:00+00:00") is True
    assert _select_flight_candidate(mission, 2, "2026-11-19T10:01:00+00:00") is True
    assert mission.artifacts["hotels"]["status"] == "stale"
    assert mission.artifacts["transfers"]["status"] == "stale"
    assert mission.artifacts["routes"]["status"] == "stale"
    assert mission.artifacts["itinerary"]["status"] == "stale"
    assert mission.artifacts["budget"]["status"] == "stale"
    assert mission.artifacts["hotels_confirmed"]["status"] == "confirmed"
    assert mission.artifacts["hotels_confirmed"]["booking_reference"] == "USER-REF"
    assert mission.selections["flights"]["selection_status"] == "selected_not_booked"


def test_price_only_flight_change_only_invalidates_budget():
    mission = TravelMission()
    mission.candidates["flights"] = [
        {"price_amount": 6000, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00"}]},
        {"price_amount": 6500, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00"}]},
    ]
    for name in ("hotels", "transfers", "routes", "itinerary", "budget"):
        mission.artifacts[name] = {"status": "current"}
    _select_flight_candidate(mission, 1, "2026-11-19T10:00:00+00:00")
    _select_flight_candidate(mission, 2, "2026-11-19T10:01:00+00:00")
    assert mission.artifacts["budget"]["status"] == "stale"
    assert mission.artifacts["hotels"]["status"] == "current"
    assert mission.artifacts["transfers"]["status"] == "current"
    assert mission.artifacts["itinerary"]["status"] == "current"


from app.tools.travel_apis import _normalise_serpapi_flights


def test_serpapi_normalizer_preserves_connecting_segments_and_layovers():
    payload = {
        "search_metadata": {
            "google_flights_url": "https://www.google.com/travel/flights",
        },
        "best_flights": [{
            "price": 7200,
            "flights": [
                {
                    "airline": "Test Air",
                    "flight_number": "TA101",
                    "departure_airport": {"id": "BHO", "time": "2026-12-20T08:00"},
                    "arrival_airport": {"id": "BOM", "time": "2026-12-20T09:30"},
                },
                {
                    "airline": "Test Air",
                    "flight_number": "TA202",
                    "departure_airport": {"id": "BOM", "time": "2026-12-20T11:00"},
                    "arrival_airport": {"id": "DEL", "time": "2026-12-20T13:00"},
                },
            ],
            "layovers": [{"id": "BOM", "duration": 90}],
            "total_duration": 300,
        }],
        "other_flights": [],
    }
    items, _ = _normalise_serpapi_flights(payload, "BHO", "DEL", "https://www.google.com/travel/flights")
    assert len(items) == 1
    assert items[0]["stops"] == 1
    assert [segment["flight_number"] for segment in items[0]["segments"]] == ["TA101", "TA202"]
    assert items[0]["segments"][0]["destination"] == "BOM"
    assert items[0]["segments"][1]["origin"] == "BOM"
    assert items[0]["layovers"][0]["id"] == "BOM"
    assert items[0]["price_amount"] == 7200
