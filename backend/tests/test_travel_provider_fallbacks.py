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
