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


def _fail_serpapi(monkeypatch):
    def fail(*args, **kwargs):
        raise travel_apis.SerpApiError("SerpApi unavailable")

    monkeypatch.setattr(travel_apis.serpapi_client, "search", fail)


def test_flight_provider_exception_returns_external_fallback(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    _fail_serpapi(monkeypatch)

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
    _fail_serpapi(monkeypatch)

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


def _serpapi_flight_payload():
    return {
        "search_metadata": {
            "status": "Success",
            "google_flights_url": "https://www.google.com/travel/flights",
        },
        "best_flights": [
            {
                "price": 5250,
                "flights": [
                    {
                        "airline": "Example Air",
                        "flight_number": "EA101",
                        "departure_airport": {
                            "id": "ORG",
                            "time": "2026-12-20 08:00",
                        },
                        "arrival_airport": {
                            "id": "DST",
                            "time": "2026-12-20 10:00",
                        },
                    }
                ],
            }
        ],
        "other_flights": [],
    }


def test_serpapi_success_returns_normalized_flight_results(monkeypatch):
    _mock_airports(monkeypatch)

    monkeypatch.setattr(
        travel_apis.serpapi_client,
        "search",
        lambda params: _serpapi_flight_payload(),
    )

    def unexpected_cli_call(*args, **kwargs):
        raise AssertionError("TRVL CLI should not run after SerpApi succeeds")

    monkeypatch.setattr(travel_apis.subprocess, "run", unexpected_cli_call)

    result = RealFlightSearchTool().execute(None, _flight_params())

    assert result.success is True
    assert result.data["type"] == "flight_list"
    assert result.data["live_inventory"] is True
    assert result.data["resolution_status"] == "success"
    assert result.data["provider"] == "serpapi_google_flights"
    assert len(result.data["items"]) == 1

    flight = result.data["items"][0]
    assert flight["price"] == "₹5,250"
    assert flight["currency"] == "INR"
    assert flight["stops"] == 0
    assert flight["segments"][0]["flight_number"] == "EA101"
    assert flight["segments"][0]["origin"] == "ORG"
    assert flight["segments"][0]["destination"] == "DST"


def test_serpapi_success_with_no_flights_returns_no_results(monkeypatch):
    _mock_airports(monkeypatch)

    monkeypatch.setattr(
        travel_apis.serpapi_client,
        "search",
        lambda params: {
            "search_metadata": {
                "status": "Success",
                "google_flights_url": "https://www.google.com/travel/flights",
            },
            "best_flights": [],
            "other_flights": [],
        },
    )

    result = RealFlightSearchTool().execute(None, _flight_params())

    assert result.success is True
    assert result.data["items"] == []
    assert result.data["live_inventory"] is True
    assert result.data["resolution_status"] == "no_results"
    assert result.data["provider"] == "serpapi_google_flights"


def test_serpapi_failure_falls_back_to_trvl_cli(monkeypatch):
    _enable_cli(monkeypatch)
    _mock_airports(monkeypatch)
    _fail_serpapi(monkeypatch)

    cli_payload = {
        "flights": [
            {
                "price": 6100,
                "currency": "INR",
                "legs": [
                    {
                        "airline": "Fallback Air",
                        "flight_number": "FA202",
                        "departure_airport": {"code": "ORG"},
                        "arrival_airport": {"code": "DST"},
                        "departure_time": "2026-12-20T09:00",
                        "arrival_time": "2026-12-20T11:00",
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(
        travel_apis.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "CompletedProcess",
            (),
            {"stdout": __import__("json").dumps(cli_payload)},
        )(),
    )

    result = RealFlightSearchTool().execute(None, _flight_params())

    assert result.success is True
    assert result.data["type"] == "flight_list"
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["segments"][0]["flight_number"] == "FA202"
