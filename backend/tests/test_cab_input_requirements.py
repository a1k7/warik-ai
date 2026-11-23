from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from app.tools.travel_apis import CabDeepLinkTool, CabInput
from app.agents.deterministic_parser import parse


def test_cab_requires_pickup_and_dropoff():
    with pytest.raises(ValidationError):
        CabInput()

    with pytest.raises(ValidationError):
        CabInput(pickup_location="Pune")


def test_cab_accepts_explicit_locations():
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Junction",
    )

    assert params.pickup_location == "VIT Bhopal"
    assert params.dropoff_location == "Bhopal Junction"


def test_uber_link_uses_both_supplied_locations():
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Junction",
    )

    url = CabDeepLinkTool._provider_url("uber", params)
    query = parse_qs(urlsplit(url).query)

    assert query["pickup[formatted_address]"] == ["VIT Bhopal"]
    assert query["dropoff[formatted_address]"] == ["Bhopal Junction"]


def test_ola_link_uses_both_supplied_locations():
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Junction",
    )

    url = CabDeepLinkTool._provider_url("ola", params)
    query = parse_qs(urlsplit(url).query)

    assert query["pickup_name"] == ["VIT Bhopal"]
    assert query["drop_name"] == ["Bhopal Junction"]


def test_cab_preferences_are_validated_and_preserved():
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Junction",
        pickup_at="2026-11-24T08:30",
        passengers=3,
        vehicle_preference="suv",
        luggage_count=2,
    )

    assert params.pickup_at == "2026-11-24T08:30"
    assert params.passengers == 3
    assert params.vehicle_preference == "suv"
    assert params.luggage_count == 2

    with pytest.raises(ValidationError):
        CabInput(
            pickup_location="VIT Bhopal",
            dropoff_location="Bhopal Junction",
            passengers=0,
        )

    with pytest.raises(ValidationError):
        CabInput(
            pickup_location="VIT Bhopal",
            dropoff_location="Bhopal Junction",
            vehicle_preference="spaceship",
        )


def test_deterministic_cab_parser_preserves_route_and_preferences():
    result = parse(
        "Book a cab from VIT Bhopal to Bhopal Junction"
        " | pickup_at=2026-11-24T08:30 | passengers=3"
        " | vehicle_preference=suv | luggage_count=2"
    )

    assert result is not None
    assert result["intent"] == "get_cab_links"
    assert result["params"] == {
        "pickup_location": "VIT Bhopal",
        "dropoff_location": "Bhopal Junction",
        "pickup_at": "2026-11-24T08:30",
        "passengers": 3,
        "vehicle_preference": "suv",
        "luggage_count": 2,
    }


def test_cab_handoff_is_not_a_confirmed_booking_or_quote():
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Junction",
        passengers=2,
    )

    result = CabDeepLinkTool().execute(None, params)
    assert result.success is True
    assert result.data["live_quote"] is False
    assert result.data["booking_created"] is False
    assert result.data["payment_processed"] is False
    assert set(result.data["links"]) == {"uber", "ola"}


def test_deterministic_cab_parser_does_not_guess_missing_locations():
    assert parse("Book me a cab") is None
    assert parse("Get me an Uber from the airport") is None
