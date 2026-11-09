
from app.agents.goal_interpreter import GoalInterpreter


def make_step(step_id, tool, params=None):
    return {
        "id": step_id,
        "description": tool,
        "tool": tool,
        "params": params or {},
        "depends_on": [],
        "approval_required": False,
        "required": True,
        "dep_policy": "all_success",
        "max_retries": 0,
    }


def test_hotel_step_is_integrated_into_advanced_itinerary():
    steps = [
        make_step(
            "itinerary",
            "generate_advanced_itinerary",
            {
                "destination": "Kochi, Munnar, Alleppey",
                "days": 4,
            },
        ),
        make_step(
            "hotels",
            "search_hotels_stayapi",
            {
                "destination": "Kochi",
                "checkin": "2026-12-10",
                "checkout": "2026-12-14",
                "travellers": 2,
            },
        ),
        make_step("summary", "compile_trip_summary"),
    ]

    result = GoalInterpreter._normalize_travel_steps(
        steps,
        {"destination": "Kochi, Munnar, Alleppey"},
    )

    itinerary = next(
        s for s in result
        if s["tool"] == "generate_advanced_itinerary"
    )

    assert itinerary["params"]["include_hotels"] is True
    assert itinerary["params"]["check_in"] == "2026-12-10"
    assert itinerary["params"]["check_out"] == "2026-12-14"
    assert itinerary["params"]["travellers"] == 2

    assert not any(
        s["tool"] == "search_hotels_stayapi"
        for s in result
    )


def test_flights_and_cabs_remain_independent():
    steps = [
        make_step(
            "itinerary",
            "generate_advanced_itinerary",
            {"destination": "Kochi", "days": 4},
        ),
        make_step(
            "flight",
            "search_flights_real",
            {
                "from": "Mumbai",
                "to": "Kochi",
                "dates": ["2026-12-10"],
            },
        ),
        make_step(
            "cab",
            "get_cab_links",
            {
                "from": "Kochi Airport",
                "to": "Munnar",
            },
        ),
        make_step("summary", "compile_trip_summary"),
    ]

    result = GoalInterpreter._normalize_travel_steps(
        steps,
        {"destination": "Kochi"},
    )

    flight = next(
        s for s in result if s["tool"] == "search_flights_real"
    )
    cab = next(
        s for s in result if s["tool"] == "get_cab_links"
    )

    assert flight["params"]["origin"] == "Mumbai"
    assert flight["params"]["destination"] == "Kochi"
    assert flight["params"]["date"] == "2026-12-10"

    assert cab["params"]["pickup_location"] == "Kochi Airport"
    assert cab["params"]["dropoff_location"] == "Munnar"

    assert flight["depends_on"] == []
    assert cab["depends_on"] == []

    assert flight["required"] is False
    assert cab["required"] is False


def test_summary_depends_on_all_discovery_steps():
    steps = [
        make_step("itinerary", "generate_advanced_itinerary"),
        make_step(
            "flight",
            "search_flights_real",
            {
                "origin": "Mumbai",
                "destination": "Kochi",
                "date": "2026-12-10",
            },
        ),
        make_step("cab", "get_cab_links"),
        make_step("summary", "compile_trip_summary"),
    ]

    result = GoalInterpreter._normalize_travel_steps(
        steps,
        {"destination": "Kerala"},
    )

    summary = next(
        s for s in result
        if s["tool"] == "compile_trip_summary"
    )

    assert summary["depends_on"] == [
        "itinerary",
        "flight",
        "cab",
    ]

    assert summary["required"] is True
    assert summary["dep_policy"] == "tolerate_failure"


def test_missing_summary_is_created():
    steps = [
        make_step("itinerary", "generate_advanced_itinerary"),
        make_step(
            "flight",
            "search_flights_real",
            {
                "origin": "Mumbai",
                "destination": "Kochi",
                "date": "2026-12-10",
            },
        ),
    ]

    result = GoalInterpreter._normalize_travel_steps(
        steps,
        {"destination": "Kochi"},
    )

    summaries = [
        s for s in result
        if s["tool"] == "compile_trip_summary"
    ]

    assert len(summaries) == 1
    assert summaries[0]["depends_on"] == [
        "itinerary",
        "flight",
    ]


def test_itinerary_without_hotel_request_does_not_enable_hotels():
    steps = [
        make_step(
            "itinerary",
            "generate_advanced_itinerary",
            {"destination": "Kochi", "days": 2},
        )
    ]

    result = GoalInterpreter._normalize_travel_steps(
        steps,
        {"destination": "Kochi"},
    )

    itinerary = result[0]

    assert itinerary["params"].get("include_hotels") is not True


def test_invalid_flight_is_skipped_from_summary_dependencies():
    steps = [
        make_step("itinerary", "generate_advanced_itinerary"),
        make_step("flight", "search_flights_real"),
        make_step("cab", "get_cab_links"),
        make_step("summary", "compile_trip_summary"),
    ]

    result = GoalInterpreter._normalize_travel_steps(
        steps,
        {"destination": "Kerala"},
    )

    assert not any(
        s["tool"] == "search_flights_real"
        for s in result
    )

    summary = next(
        s for s in result
        if s["tool"] == "compile_trip_summary"
    )

    assert summary["depends_on"] == [
        "itinerary",
        "cab",
    ]
