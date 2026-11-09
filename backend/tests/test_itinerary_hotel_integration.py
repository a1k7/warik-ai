import pytest

from app.tools import trip_tools
from app.tools.base import ToolResult
from app.tools.trip_tools import (
    GenerateAdvancedItineraryTool,
    ItineraryInput,
)


CITIES = [
    {
        "name": "Kochi",
        "state": "Kerala",
        "country": "India",
        "lat": 9.9312,
        "lon": 76.2673,
        "type": "city",
    },
    {
        "name": "Munnar",
        "state": "Kerala",
        "country": "India",
        "lat": 10.0889,
        "lon": 77.0595,
        "type": "city",
    },
    {
        "name": "Alleppey",
        "state": "Kerala",
        "country": "India",
        "lat": 9.4981,
        "lon": 76.3388,
        "type": "city",
    },
]


class FakeHotelTool:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def execute(self, ctx, params):
        self.calls.append(params)

        response = self.responses.get(
            params.city,
            ToolResult(
                success=True,
                message="Hotels found.",
                data={
                    "type": "hotel_list",
                    "items": [
                        {
                            "name": f"{params.city} Test Hotel",
                            "address": f"{params.city}, Kerala",
                            "total_stay": "₹5,000",
                            "price_per_night": "₹2,500",
                            "booking_url": "https://example.com/hotel",
                            "image_url": "https://example.com/hotel.jpg",
                        }
                    ],
                },
            ),
        )

        if isinstance(response, Exception):
            raise response

        return response


@pytest.fixture
def setup_itinerary(monkeypatch):
    fake_hotel_tool = FakeHotelTool()

    monkeypatch.setattr(
        trip_tools,
        "_geocode_destination",
        lambda destination: (CITIES, None),
    )

    monkeypatch.setattr(
        trip_tools,
        "_fetch_places",
        lambda *args, **kwargs: [],
    )

    monkeypatch.setattr(
        trip_tools,
        "_generate_descriptions",
        lambda *args, **kwargs: {},
    )

    monkeypatch.setattr(
        trip_tools,
        "StayApiHotelTool",
        lambda: fake_hotel_tool,
    )

    return fake_hotel_tool


def make_params(**overrides):
    values = {
        "destination": "Kochi, Munnar, Alleppey",
        "days": 4,
        "travellers": 2,
        "include_hotels": True,
        "check_in": "2026-12-10",
        "check_out": "2026-12-14",
    }
    values.update(overrides)
    return ItineraryInput(**values)


def test_hotel_search_uses_city_specific_dates(setup_itinerary):
    result = GenerateAdvancedItineraryTool().execute(
        None,
        make_params(),
    )

    assert result.success is True
    assert len(setup_itinerary.calls) == 3

    actual = [
        (
            call.city,
            call.check_in,
            call.check_out,
        )
        for call in setup_itinerary.calls
    ]

    assert actual == [
        ("Kochi", "2026-12-10", "2026-12-12"),
        ("Munnar", "2026-12-12", "2026-12-13"),
        ("Alleppey", "2026-12-13", "2026-12-14"),
    ]


def test_hotel_results_are_mapped_into_itinerary(setup_itinerary):
    result = GenerateAdvancedItineraryTool().execute(
        None,
        make_params(),
    )

    assert result.success is True

    hotels = result.data["hotels"]

    assert len(hotels) == 3

    kochi_hotel = hotels[0]

    assert kochi_hotel["name"] == "Kochi Test Hotel (Kochi)"
    assert kochi_hotel["city"] == "Kochi"
    assert kochi_hotel["check_in"] == "2026-12-10"
    assert kochi_hotel["check_out"] == "2026-12-12"
    assert kochi_hotel["price"] == "₹5,000"
    assert kochi_hotel["price_per_night"] == "₹2,500"
    assert kochi_hotel["booking_url"] == "https://example.com/hotel"


def test_empty_hotel_results_do_not_fail_itinerary(
    setup_itinerary,
):
    setup_itinerary.responses = {
        "Munnar": ToolResult(
            success=True,
            message="No hotels found.",
            data={
                "type": "hotel_list",
                "items": [],
            },
        )
    }

    result = GenerateAdvancedItineraryTool().execute(
        None,
        make_params(),
    )

    assert result.success is True

    assert len(result.data["hotels"]) == 2

    assert any(
        "Munnar" in note and "No hotels found" in note
        for note in result.data["notes"]
    )


def test_provider_failure_in_one_city_does_not_stop_other_searches(
    setup_itinerary,
):
    setup_itinerary.responses = {
        "Munnar": ToolResult(
            success=False,
            message="Hotel provider unavailable.",
            data=None,
        )
    }

    result = GenerateAdvancedItineraryTool().execute(
        None,
        make_params(),
    )

    assert result.success is True

    # All three cities should still have been attempted.
    assert len(setup_itinerary.calls) == 3

    # Kochi and Alleppey results should remain available.
    assert len(result.data["hotels"]) == 2

    assert any(
        "Munnar" in note and "Hotel provider unavailable" in note
        for note in result.data["notes"]
    )


def test_checkout_mismatch_skips_hotel_provider_calls(
    setup_itinerary,
):
    result = GenerateAdvancedItineraryTool().execute(
        None,
        make_params(check_out="2026-12-13"),
    )

    assert result.success is True
    assert setup_itinerary.calls == []
    assert result.data["hotels"] == []

    assert any(
        "checkout date does not match" in note
        for note in result.data["notes"]
    )


def test_hotel_search_disabled_makes_no_provider_calls(
    setup_itinerary,
):
    result = GenerateAdvancedItineraryTool().execute(
        None,
        make_params(include_hotels=False),
    )

    assert result.success is True
    assert setup_itinerary.calls == []
    assert result.data["hotels"] == []
