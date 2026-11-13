from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from app.tools.travel_apis import CabDeepLinkTool, CabInput


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
