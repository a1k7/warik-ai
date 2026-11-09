
from app.tools.trip_summary_tool import (
    CompileTripSummaryInput,
    CompileTripSummaryTool,
)


def test_summary_extracts_hotels_from_itinerary():
    hotel = {
        "name": "Kochi Test Hotel",
        "city": "Kochi",
        "check_in": "2026-12-10",
        "check_out": "2026-12-12",
        "price": "₹5,000",
        "booking_url": "https://example.com/kochi",
    }

    params = CompileTripSummaryInput(
        destination="Kerala",
        dependency_results={
            "step1": {
                "tool": "generate_advanced_itinerary",
                "result": {
                    "hotels": [hotel],
                    "days": [],
                    "notes": [],
                },
            }
        },
    )

    result = CompileTripSummaryTool().execute(None, params)

    assert result.success is True
    assert result.data["hotels"] == [hotel]
    assert result.data["itinerary"]["hotels"] == [hotel]


def test_summary_preserves_standalone_hotel_results():
    hotel = {
        "name": "Munnar Hotel",
        "city": "Munnar",
        "booking_url": "https://example.com/munnar",
    }

    params = CompileTripSummaryInput(
        dependency_results={
            "step1": {
                "tool": "search_hotels_stayapi",
                "result": {"items": [hotel]},
            }
        },
    )

    result = CompileTripSummaryTool().execute(None, params)

    assert result.success is True
    assert result.data["hotels"] == [hotel]


def test_summary_deduplicates_hotels():
    hotel = {
        "name": "Kochi Hotel",
        "city": "Kochi",
        "booking_url": "https://example.com/kochi",
    }

    params = CompileTripSummaryInput(
        dependency_results={
            "step1": {
                "tool": "generate_advanced_itinerary",
                "result": {"hotels": [hotel]},
            },
            "step2": {
                "tool": "search_hotels_stayapi",
                "result": {"items": [hotel]},
            },
        },
    )

    result = CompileTripSummaryTool().execute(None, params)

    assert len(result.data["hotels"]) == 1


def test_summary_preserves_flights_and_cabs():
    flight = {"price": "₹8,000"}
    cab = {"uber": "https://example.com/uber"}

    params = CompileTripSummaryInput(
        dependency_results={
            "flight_step": {
                "tool": "search_flights_real",
                "result": {"items": [flight]},
            },
            "cab_step": {
                "tool": "get_cab_links",
                "result": {"links": cab},
            },
        },
    )

    result = CompileTripSummaryTool().execute(None, params)

    assert result.data["flights"] == [flight]
    assert result.data["cabs"] == cab


def test_summary_includes_hotel_search_issues():
    params = CompileTripSummaryInput(
        dependency_results={
            "step1": {
                "tool": "generate_advanced_itinerary",
                "result": {
                    "hotels": [],
                    "notes": [
                        "Hotel search issue: Munnar: Provider unavailable."
                    ],
                },
            }
        },
    )

    result = CompileTripSummaryTool().execute(None, params)

    assert len(result.data["failures"]) == 1
    assert result.data["failures"][0]["tool"] == "hotel_search"
    assert "Munnar" in result.data["failures"][0]["error"]


def test_summary_preserves_dependency_failures():
    params = CompileTripSummaryInput(
        dependency_failures={
            "flight_step": {
                "tool": "search_flights_real",
                "error": "Flight provider unavailable.",
            }
        },
    )

    result = CompileTripSummaryTool().execute(None, params)

    assert result.data["failures"] == [
        {
            "tool": "search_flights_real",
            "error": "Flight provider unavailable.",
        }
    ]


def test_summary_handles_empty_dependencies():
    result = CompileTripSummaryTool().execute(
        None,
        CompileTripSummaryInput(),
    )

    assert result.success is True
    assert result.data["flights"] == []
    assert result.data["hotels"] == []
    assert result.data["cabs"] == {}
    assert result.data["itinerary"] is None
    assert result.data["failures"] == []
