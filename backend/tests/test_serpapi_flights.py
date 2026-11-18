from datetime import date

from app.browser_agent.flights import (
    _normalise_flight,
    airport_ids,
    requested_date,
    requested_time_range,
)


def test_indian_city_airport_aliases():
    assert airport_ids("Bengaluru") == "BLR"
    assert airport_ids("Goa") == "GOI,GOX"
    assert airport_ids("DEL") == "DEL"


def test_relative_and_iso_departure_dates():
    today = date(2026, 11, 18)
    assert requested_date("tomorrow evening", today) == date(2026, 11, 19)
    assert requested_date("day after tomorrow", today) == date(2026, 11, 20)
    assert requested_date("fly on 2026-11-22", today) == date(2026, 11, 22)


def test_evening_filter_uses_serpapi_hour_range():
    assert requested_time_range("tomorrow evening") == "17,23"
    assert requested_time_range("tomorrow morning") == "5,12"
    assert requested_time_range("tomorrow") is None


def test_normalizer_rejects_connecting_flights():
    connecting = {
        "flights": [
            {"airline": "Example", "flight_number": "EX1", "departure_airport": {}, "arrival_airport": {}, "duration": 60},
            {"airline": "Example", "flight_number": "EX2", "departure_airport": {}, "arrival_airport": {}, "duration": 60},
        ],
        "layovers": [{"name": "Hub"}],
        "price": 1000,
    }
    assert _normalise_flight(connecting) is None


def test_normalizer_keeps_real_provider_fare_and_segment():
    nonstop = {
        "flights": [{
            "airline": "Example Air",
            "flight_number": "EX123",
            "departure_airport": {"id": "BLR", "time": "2026-11-19 18:10"},
            "arrival_airport": {"id": "GOI", "time": "2026-11-19 19:30"},
            "duration": 80,
        }],
        "layovers": [],
        "price": 4200,
    }
    result = _normalise_flight(nonstop)
    assert result["airline"] == "Example Air"
    assert result["flight_number"] == "EX123"
    assert result["price"] == 4200
    assert result["stops"] == 0
