from datetime import date, timedelta

import pytest

from app.agents.goal_interpreter import (
    GoalInterpreter,
    TravelClarificationRequired,
)


def _iso(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def _travel_steps(*, origin="", flight_date="", check_in="", check_out=""):
    return [
        {
            "id": "itinerary",
            "tool": "generate_advanced_itinerary",
            "description": "Prepare the Goa itinerary and requested stay search.",
            "params": {
                "destination": "Goa",
                "days": 3,
                "include_hotels": True,
                "check_in": check_in or None,
                "check_out": check_out or None,
            },
            "depends_on": [],
        },
        {
            "id": "flights",
            "tool": "search_flights_real",
            "description": "Search flights to Goa.",
            "params": {
                "origin": origin,
                "destination": "Goa",
                "date": flight_date,
            },
            "depends_on": [],
        },
    ]


def test_explicit_flight_request_asks_for_missing_origin_and_dates():
    with pytest.raises(TravelClarificationRequired) as exc:
        GoalInterpreter._normalize_travel_steps(
            _travel_steps(),
            {"destination": "Goa"},
        )

    message = str(exc.value).lower()
    assert "departure city" in message
    assert "trip start date" in message
    assert "hotel check-out date" in message


def test_explicit_flight_request_does_not_silently_drop_missing_origin():
    check_in, check_out = _iso(20), _iso(23)
    with pytest.raises(TravelClarificationRequired) as exc:
        GoalInterpreter._normalize_travel_steps(
            _travel_steps(check_in=check_in, check_out=check_out),
            {"destination": "Goa", "check_in": check_in, "check_out": check_out},
        )

    assert "departure city" in str(exc.value).lower()


def test_hotel_checkin_date_is_used_as_outbound_date_when_flight_date_omitted():
    check_in, check_out = _iso(20), _iso(23)
    normalized = GoalInterpreter._normalize_travel_steps(
        _travel_steps(
            origin="Ahmedabad",
            check_in=check_in,
            check_out=check_out,
        ),
        {"destination": "Goa", "check_in": check_in, "check_out": check_out},
    )

    flight = next(step for step in normalized if step["tool"] == "search_flights_real")
    assert flight["params"]["origin"] == "Ahmedabad"
    assert flight["params"]["destination"] == "Goa"
    assert flight["params"]["date"] == check_in
    assert flight["required"] is False
    assert "compile_trip_summary" in [step["tool"] for step in normalized]


def test_explicit_flight_request_without_date_or_hotel_dates_asks_for_departure_date():
    with pytest.raises(TravelClarificationRequired) as exc:
        GoalInterpreter._normalize_travel_steps(
            [
                {
                    "id": "itinerary",
                    "tool": "generate_advanced_itinerary",
                    "params": {"destination": "Goa", "days": 3, "include_hotels": False},
                    "depends_on": [],
                },
                {
                    "id": "flights",
                    "tool": "search_flights_real",
                    "params": {"origin": "Ahmedabad", "destination": "Goa", "date": ""},
                    "depends_on": [],
                },
            ],
            {"destination": "Goa"},
        )

    assert "departure date" in str(exc.value).lower()


def test_itinerary_without_explicit_flight_request_does_not_ask_for_departure_city():
    normalized = GoalInterpreter._normalize_travel_steps(
        [
            {
                "id": "itinerary",
                "tool": "generate_advanced_itinerary",
                "params": {"destination": "Goa", "days": 3, "include_hotels": False},
                "depends_on": [],
            }
        ],
        {"destination": "Goa"},
    )

    tools = [step["tool"] for step in normalized]
    assert "generate_advanced_itinerary" in tools
    assert "search_flights_real" not in tools
