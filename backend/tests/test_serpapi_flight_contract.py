from app.tools.travel_apis import (
    FlightInput,
    _normalise_serpapi_flights,
)


def _segment(origin, destination, number, departure):
    return {
        "airline": "Example Air",
        "flight_number": number,
        "departure_airport": {
            "id": origin,
            "time": departure,
        },
        "arrival_airport": {
            "id": destination,
            "time": "2026-12-10 12:00",
        },
        "duration": 90,
    }


def _flight(price, segments, layovers=None):
    return {
        "price": price,
        "flights": segments,
        "layovers": layovers or [],
        "total_duration": 240,
    }


def _payload(*flights):
    return {
        "search_metadata": {
            "status": "Success",
            "google_flights_url": "https://www.google.com/travel/flights",
            "created_at": "2026-12-01 10:00:00 UTC",
        },
        "best_flights": list(flights),
        "other_flights": [],
    }


def test_normalizer_accepts_verified_connecting_flight():
    connecting = _flight(
        42000,
        [
            _segment("BLR", "BOM", "EX101", "2026-12-10 08:00"),
            _segment("BOM", "GOI", "EX202", "2026-12-10 10:30"),
        ],
        layovers=[
            {"id": "BOM", "name": "Mumbai", "duration": 60}
        ],
    )

    items, _ = _normalise_serpapi_flights(
        _payload(connecting),
        "BLR",
        "GOI",
        "https://www.google.com/travel/flights?q=BLR+GOI",
    )

    assert len(items) == 1
    assert items[0]["stops"] == 1
    assert len(items[0]["segments"]) == 2
    assert items[0]["price_amount"] == 42000
    assert items[0]["currency"] == "INR"
    assert items[0]["provider"] == "serpapi_google_flights"
    assert items[0]["retrieved_at"] == "2026-12-01 10:00:00 UTC"


def test_normalizer_sorts_by_numeric_price_not_display_string():
    expensive = _flight(
        150000,
        [_segment("BLR", "GOI", "EX150", "2026-12-10 09:00")],
    )
    cheaper = _flight(
        25000,
        [_segment("BLR", "GOI", "EX025", "2026-12-10 08:00")],
    )

    items, _ = _normalise_serpapi_flights(
        _payload(expensive, cheaper),
        "BLR",
        "GOI",
        "https://www.google.com/travel/flights",
    )

    assert [item["price_amount"] for item in items] == [25000, 150000]


def test_normalizer_rejects_disconnected_segments():
    disconnected = _flight(
        42000,
        [
            _segment("BLR", "BOM", "EX101", "2026-12-10 08:00"),
            _segment("DEL", "GOI", "EX202", "2026-12-10 10:30"),
        ],
        layovers=[
            {"id": "BOM", "name": "Mumbai", "duration": 60}
        ],
    )

    items, _ = _normalise_serpapi_flights(
        _payload(disconnected),
        "BLR",
        "GOI",
        "https://www.google.com/travel/flights",
    )

    assert items == []


def test_normalizer_accepts_multiple_requested_airport_codes():
    flight = _flight(
        5000,
        [_segment("GOX", "BLR", "EX501", "2026-12-10 09:00")],
    )

    items, _ = _normalise_serpapi_flights(
        _payload(flight),
        "GOI,GOX",
        "BLR",
        "https://www.google.com/travel/flights",
    )

    assert len(items) == 1
    assert items[0]["segments"][0]["origin"] == "GOX"


def test_flight_input_exposes_passengers_cabin_and_stop_preferences():
    params = FlightInput(
        origin="Bengaluru",
        destination="Goa",
        date="2026-12-10",
        adults=2,
        children=1,
        travel_class=3,
        max_stops=1,
        currency="INR",
        outbound_times="6,12",
    )

    assert params.adults == 2
    assert params.children == 1
    assert params.travel_class == 3
    assert params.max_stops == 1
    assert params.outbound_times == "6,12"


def test_flight_input_rejects_invalid_cabin_and_stop_count():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FlightInput(
            origin="Bengaluru",
            destination="Goa",
            date="2026-12-10",
            travel_class=5,
        )

    with pytest.raises(ValidationError):
        FlightInput(
            origin="Bengaluru",
            destination="Goa",
            date="2026-12-10",
            max_stops=3,
        )
