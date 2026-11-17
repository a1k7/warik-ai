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


def _flight_params():
    return FlightInput(
        origin="Origin Place",
        destination="Destination Place",
        date="2026-12-20",
    )


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



def _flight(code_from, code_to, departure, price=100, currency="INR"):
    return {
        "price": price,
        "currency": currency,
        "legs": [{
            "airline": "Example Air",
            "flight_number": "EX101",
            "departure_airport": {"code": code_from},
            "arrival_airport": {"code": code_to},
            "departure_time": departure,
            "arrival_time": departure,
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
