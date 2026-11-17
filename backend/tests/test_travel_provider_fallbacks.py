import json
from types import SimpleNamespace

from app.tools import travel_apis
from app.tools.travel_apis import (
    FlightInput,
    HotelInput,
    RealFlightSearchTool,
    StayApiHotelTool,
)


def _airport(code):
    return {
        "iata": code,
        "name": f"{code} Airport",
        "lat": 0.0,
        "lon": 0.0,
        "distance_km": 0.0,
    }


def _flight_params(**overrides):
    values = {
        "origin": "Origin Place",
        "destination": "Destination Place",
        "date": "2026-12-20",
    }
    values.update(overrides)
    return FlightInput(**values)


def _hotel_params(**overrides):
    values = {
        "city": "Example City",
        "check_in": "2026-12-10",
        "check_out": "2026-12-12",
        "travellers": 2,
    }
    values.update(overrides)
    return HotelInput(**values)


def _enable_cli(monkeypatch):
    monkeypatch.setattr(travel_apis.settings, "duffel_api_key", "")
    monkeypatch.setattr(
        travel_apis.shutil,
        "which",
        lambda _: "/usr/bin/trvl",
    )


def _mock_airports(monkeypatch):
    airports = {
        "Origin Place": [_airport("ORG")],
        "Destination Place": [_airport("DST")],
    }
    monkeypatch.setattr(
        travel_apis,
        "resolve_airport_candidates",
        lambda location: airports[location],
    )


def test_flight_provider_exception_returns_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)

    def fail_provider(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(travel_apis.subprocess, "run", fail_provider)

    result = RealFlightSearchTool().execute(None, _flight_params())

    assert result.success is True
    assert result.data["type"] == "flight_list"
    assert result.data["items"] == []
    assert result.data["live_inventory"] is False
    assert result.data["resolution_status"] == "provider_unavailable"
    assert result.data["provider_error"] == "provider unavailable"
    assert "google.com/travel/flights" in result.data["search_url"]
    assert result.data["origin_airport"]["iata"] == "ORG"
    assert result.data["destination_airport"]["iata"] == "DST"


def test_flight_no_results_returns_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)

    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps({"flights": []})),
    )

    result = RealFlightSearchTool().execute(None, _flight_params())

    assert result.success is True
    assert result.data["items"] == []
    assert result.data["live_inventory"] is True
    assert result.data["resolution_status"] == "no_results"
    assert "google.com/travel/flights" in result.data["search_url"]


def test_hotel_provider_exception_returns_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)

    def fail_provider(*args, **kwargs):
        raise RuntimeError("hotel provider unavailable")

    monkeypatch.setattr(travel_apis.subprocess, "run", fail_provider)

    result = StayApiHotelTool().execute(None, _hotel_params())

    assert result.success is True
    assert result.data["type"] == "hotel_list"
    assert result.data["items"] == []
    assert result.data["live_inventory"] is False
    assert result.data["resolution_status"] == "provider_unavailable"
    assert result.data["provider_error"] == "hotel provider unavailable"
    assert "booking.com/searchresults.html" in result.data["search_url"]


def test_hotel_invalid_json_returns_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)

    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="not valid JSON"),
    )

    result = StayApiHotelTool().execute(None, _hotel_params())

    assert result.success is True
    assert result.data["items"] == []
    assert result.data["live_inventory"] is False
    assert result.data["resolution_status"] == "invalid_provider_response"
    assert "booking.com/searchresults.html" in result.data["search_url"]


def test_hotel_no_results_returns_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)

    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps({"hotels": []})),
    )

    result = StayApiHotelTool().execute(None, _hotel_params())

    assert result.success is True
    assert result.data["items"] == []
    assert result.data["live_inventory"] is True
    assert result.data["resolution_status"] == "no_results"
    assert "booking.com/searchresults.html" in result.data["search_url"]


def test_hotel_budget_filtered_results_return_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)

    hotels = [
        {
            "name": "Test Hotel",
            "address": "Example City",
            "price": 5000,
            "currency": "INR",
        }
    ]

    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps({"hotels": hotels})),
    )

    result = StayApiHotelTool().execute(
        None,
        _hotel_params(budget=1000),
    )

    assert result.success is True
    assert result.data["items"] == []
    assert result.data["live_inventory"] is True
    assert result.data["resolution_status"] == "budget_filtered"
    assert "booking.com/searchresults.html" in result.data["search_url"]



def _flight(code_from, code_to, departure, price=100, currency="INR", arrival=None):
    return {
        "price": price,
        "currency": currency,
        "legs": [{
            "airline": "Example Air",
            "flight_number": "EX101",
            "departure_airport": {"code": code_from},
            "arrival_airport": {"code": code_to},
            "departure_time": departure,
            "arrival_time": arrival or departure,
        }],
    }


def test_flight_search_filters_by_origin_local_departure_window(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    payload = {
        "flights": [
            _flight("ORG", "DST", "2026-12-20T07:15:00+05:30", 400),
            _flight("ORG", "DST", "2026-12-20T19:10:00+05:30", 900),
            _flight("ORG", "DST", "2026-12-20T21:45:00+05:30", 700),
        ]
    }
    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )

    result = RealFlightSearchTool().execute(
        None,
        _flight_params(departure_time_from="18:00", departure_time_to="22:00"),
    )

    assert result.success is True
    assert [item["departure_time"] for item in result.data["items"]] == [
        "2026-12-20 19:10",
        "2026-12-20 21:45",
    ]
    assert result.data["filters_applied"]["departure_time_from"] == "18:00"


def test_flight_search_handles_time_window_crossing_midnight(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    payload = {
        "flights": [
            _flight("ORG", "DST", "2026-12-20T23:20:00+05:30", 600),
            _flight("ORG", "DST", "2026-12-20T00:40:00+05:30", 500),
            _flight("ORG", "DST", "2026-12-20T14:00:00+05:30", 300),
        ]
    }
    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )

    result = RealFlightSearchTool().execute(
        None,
        _flight_params(departure_time_from="22:00", departure_time_to="02:00"),
    )

    assert [item["departure_time"].split(" ")[1] for item in result.data["items"]] == [
        "23:20",
        "00:40",
    ]


def test_flight_search_reports_when_time_filter_removes_all_provider_options(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    payload = {"flights": [_flight("ORG", "DST", "2026-12-20T07:15:00+05:30")]}
    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )

    result = RealFlightSearchTool().execute(
        None,
        _flight_params(departure_time_from="18:00", departure_time_to="22:00"),
    )

    assert result.data["items"] == []
    assert result.data["resolution_status"] == "time_filter_no_results"
    assert result.data["live_inventory"] is True


def test_flight_search_forwards_explicit_cabin_and_stop_preferences(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    calls = []

    def mock_run(command, **kwargs):
        calls.append(command)
        payload = {"flights": [_flight("ORG", "DST", "2026-12-20T19:10:00+05:30")]}
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(travel_apis.subprocess, "run", mock_run)
    params = _flight_params(cabin_class="business", stops="nonstop")
    RealFlightSearchTool().execute(None, params)

    command = calls[0]
    assert command[command.index("--cabin") + 1] == "business"
    assert command[command.index("--stops") + 1] == "nonstop"



def _flight_with_segments(*codes, departure="2026-12-20T19:10:00+05:30", price=100):
    legs = []
    for index in range(len(codes) - 1):
        legs.append({
            "airline": "Example Air",
            "flight_number": f"EX{100 + index}",
            "departure_airport": {"code": codes[index]},
            "arrival_airport": {"code": codes[index + 1]},
            "departure_time": departure,
            "arrival_time": departure,
        })
    return {"price": price, "currency": "INR", "legs": legs}


def test_flight_search_filters_maximum_stop_count_without_undocumented_cli_flag(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    calls = []
    payload = {
        "flights": [
            _flight_with_segments("ORG", "DST", price=700),
            _flight_with_segments("ORG", "HUB", "DST", price=500),
            _flight_with_segments("ORG", "HUB", "HUB2", "DST", price=300),
        ]
    }

    def mock_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(travel_apis.subprocess, "run", mock_run)
    result = RealFlightSearchTool().execute(None, _flight_params(stops="1"))

    assert [item["stops"] for item in result.data["items"]] == [0, 1]
    assert "--stops" not in calls[0]


def test_flight_search_stops_at_nonstop_when_requested(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    calls = []
    payload = {
        "flights": [
            _flight_with_segments("ORG", "DST"),
            _flight_with_segments("ORG", "HUB", "DST"),
        ]
    }

    def mock_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(travel_apis.subprocess, "run", mock_run)
    result = RealFlightSearchTool().execute(None, _flight_params(stops="nonstop"))

    assert [item["stops"] for item in result.data["items"]] == [0]
    assert calls[0][calls[0].index("--stops") + 1] == "nonstop"



def test_duffel_search_maps_live_offers_to_flight_cards(monkeypatch):
    monkeypatch.setattr(travel_apis.settings, "duffel_api_key", "test-duffel-token")
    _mock_airports(monkeypatch)
    calls = []
    offer = {
        "id": "off_test123",
        "total_amount": "6400.00",
        "total_currency": "INR",
        "expires_at": "2026-12-20T10:30:00Z",
        "owner": {"name": "Example Airline"},
        "slices": [{
            "segments": [{
                "origin": {"iata_code": "ORG", "name": "Origin Airport"},
                "destination": {"iata_code": "DST", "name": "Destination Airport"},
                "departing_at": "2026-12-20T05:30:00+05:30",
                "arriving_at": "2026-12-20T08:10:00+05:30",
                "operating_carrier": {"name": "Example Operating Carrier"},
                "marketing_carrier_flight_number": "EX101",
            }]
        }],
    }

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"data": {"id": "orq_test123", "offers": [offer]}}

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(travel_apis.httpx, "Client", Client)
    result = RealFlightSearchTool().execute(None, _flight_params(passengers=2))

    assert result.success
    assert result.data["source"] == "Duffel"
    assert result.data["offer_request_id"] == "orq_test123"
    assert result.data["live_inventory"] is True
    assert result.data["items"][0]["offer_id"] == "off_test123"
    assert result.data["items"][0]["price"] == "₹6,400"
    assert result.data["items"][0]["segments"][0]["airline"] == "Example Operating Carrier"
    assert result.data["items"][0]["departure_time"] == "2026-12-20 05:30"
    body = calls[0][1]["json"]["data"]
    assert len(body["passengers"]) == 2
    assert body["slices"][0]["departure_date"] == "2026-12-20"


def test_duffel_search_sends_time_window_and_stops(monkeypatch):
    monkeypatch.setattr(travel_apis.settings, "duffel_api_key", "test-duffel-token")
    _mock_airports(monkeypatch)
    calls = []

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"data": {"offers": []}}

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, **kwargs):
            calls.append(kwargs)
            return Response()

    monkeypatch.setattr(travel_apis.httpx, "Client", Client)
    result = RealFlightSearchTool().execute(
        None,
        _flight_params(departure_time_from="06:00", departure_time_to="09:00", stops="nonstop"),
    )
    assert result.success
    request_data = calls[0]["json"]["data"]
    assert request_data["slices"][0]["departure_time"] == {"from": "06:00", "to": "09:00"}
    assert request_data["max_connections"] == 0



def test_flight_search_filters_by_destination_arrival_window(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    payload = {
        "flights": [
            _flight("ORG", "DST", "2026-12-20T05:00:00+05:30", 600, arrival="2026-12-20T08:30:00+05:30"),
            _flight("ORG", "DST", "2026-12-20T07:00:00+05:30", 500, arrival="2026-12-20T10:30:00+05:30"),
        ]
    }
    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )

    result = RealFlightSearchTool().execute(
        None,
        _flight_params(arrival_time_to="09:00"),
    )

    assert result.success
    assert [item["arrival_time"] for item in result.data["items"]] == [
        "2026-12-20 08:30"
    ]


def test_duffel_search_filters_by_destination_arrival_time_and_does_not_invent_stops(monkeypatch):
    monkeypatch.setattr(travel_apis.settings, "duffel_api_key", "test-duffel-token")
    _mock_airports(monkeypatch)
    calls = []
    offers = [
        {
            "id": "off_early",
            "total_amount": "6400.00",
            "total_currency": "INR",
            "slices": [{
                "segments": [{
                    "origin": {"iata_code": "ORG"},
                    "destination": {"iata_code": "DST"},
                    "departing_at": "2026-12-20T05:30:00+05:30",
                    "arriving_at": "2026-12-20T08:10:00+05:30",
                    "operating_carrier": {"name": "Example Air"},
                }]
            }],
        },
        {
            "id": "off_late",
            "total_amount": "5900.00",
            "total_currency": "INR",
            "slices": [{
                "segments": [{
                    "origin": {"iata_code": "ORG"},
                    "destination": {"iata_code": "DST"},
                    "departing_at": "2026-12-20T07:30:00+05:30",
                    "arriving_at": "2026-12-20T10:30:00+05:30",
                    "operating_carrier": {"name": "Example Air"},
                }]
            }],
        },
    ]

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"data": {"offers": offers}}

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def post(self, url, **kwargs):
            calls.append(kwargs)
            return Response()

    monkeypatch.setattr(travel_apis.httpx, "Client", Client)
    result = RealFlightSearchTool().execute(
        None,
        _flight_params(arrival_time_to="09:00"),
    )

    assert result.success
    assert [item["offer_id"] for item in result.data["items"]] == ["off_early"]
    request_data = calls[0]["json"]["data"]
    assert request_data["slices"][0]["arrival_time"] == {"to": "09:00"}
    assert "max_connections" not in request_data


def test_flight_offer_refresh_retrieves_latest_price_without_booking(monkeypatch):
    from app.tools.travel_apis import RefreshFlightOfferInput, RefreshFlightOfferTool

    monkeypatch.setattr(travel_apis.settings, "duffel_api_key", "test-duffel-token")
    calls = []

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "data": {
                    "id": "off_test123",
                    "total_amount": "7100.00",
                    "total_currency": "INR",
                    "slices": [{
                        "segments": [{
                            "origin": {"iata_code": "ORG"},
                            "destination": {"iata_code": "DST"},
                            "departing_at": "2026-12-20T05:30:00+05:30",
                            "arriving_at": "2026-12-20T08:10:00+05:30",
                            "operating_carrier": {"name": "Example Air"},
                        }]
                    }],
                }
            }

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(travel_apis.httpx, "Client", Client)
    result = RefreshFlightOfferTool().execute(
        None, RefreshFlightOfferInput(offer_id="off_test123")
    )

    assert result.success
    assert result.data["refreshed"] is True
    assert result.data["items"][0]["price"] == "₹7,100"
    assert result.data["items"][0]["offer_id"] == "off_test123"
    assert "/air/offers/off_test123" in calls[0][0]
    assert "booking" in result.message.lower()
