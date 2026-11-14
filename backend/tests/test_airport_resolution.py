
from app.tools import travel_apis


class FakePlaces:
    def __init__(self, airports=None, code_records=None, error=None):
        self.airports = airports or []
        self.code_records = code_records or []
        self.error = error
        self.search_calls = []

    def search_airports(self, location, *, limit, radius_m):
        if self.error:
            raise self.error
        self.search_calls.append(location)
        return self.airports

    def search_airports_by_iata(self, iata, *, limit):
        if self.error:
            raise self.error
        return [
            item for item in self.code_records
            if item.get("iata") == iata
        ]


def test_airport_resolution_searches_multiple_geocoding_matches(monkeypatch):
    locations = [
        {"name": "First match", "display_name": "First match", "lat": 10, "lon": 10},
        {"name": "Second match", "display_name": "Second match", "lat": 20, "lon": 20},
    ]

    class FakeGeocoder:
        def search(self, query, limit=5):
            assert query == "Ambiguous worldwide place"
            assert limit == 5
            return locations

    places = FakePlaces(airports=[
        {"name": "Airport A", "iata": "AAA", "lat": 10.1, "lon": 10},
        {"name": "Airport B", "iata": "BBB", "lat": 20.1, "lon": 20},
    ])

    monkeypatch.setattr(travel_apis, "geocoder", lambda: FakeGeocoder())
    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    result = travel_apis.resolve_airport_candidates(
        "Ambiguous worldwide place"
    )

    assert {item["iata"] for item in result} == {"AAA", "BBB"}
    assert len(places.search_calls) == 2


def test_airport_resolution_ranks_nearest_airport(monkeypatch):
    class FakeGeocoder:
        def search(self, query, limit=5):
            return [{"name": query, "lat": 48.0, "lon": 2.0}]

    places = FakePlaces(airports=[
        {"name": "Far airport", "iata": "XYZ", "lat": 48.1, "lon": 2.0},
        {"name": "Near airport", "iata": "ABC", "lat": 48.01, "lon": 2.0},
    ])

    monkeypatch.setattr(travel_apis, "geocoder", lambda: FakeGeocoder())
    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    result = travel_apis.resolve_airport_candidates("Arbitrary location")

    assert [item["iata"] for item in result] == ["ABC", "XYZ"]


def test_airport_resolution_ignores_records_without_iata(monkeypatch):
    class FakeGeocoder:
        def search(self, query, limit=5):
            return [{"name": query, "lat": 10.0, "lon": 20.0}]

    places = FakePlaces(airports=[
        {"name": "Airport without code", "iata": "", "lat": 10.1, "lon": 20.1}
    ])

    monkeypatch.setattr(travel_apis, "geocoder", lambda: FakeGeocoder())
    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    assert travel_apis.resolve_airport_candidates("Unknown location") == []


def test_explicit_iata_is_verified_against_provider(monkeypatch):
    places = FakePlaces(code_records=[
        {"name": "Verified airport", "iata": "JFK", "lat": 40.6, "lon": -73.7}
    ])

    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    result = travel_apis.resolve_airport_candidates("JFK")

    assert len(result) == 1
    assert result[0]["iata"] == "JFK"
    assert result[0]["source"] == "OpenStreetMap"


def test_unverified_iata_is_not_accepted(monkeypatch):
    places = FakePlaces(code_records=[])

    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    assert travel_apis.resolve_airport_candidates("ZZZ") == []


def test_provider_failure_is_distinguished_from_no_airport(monkeypatch):
    class FakeGeocoder:
        def search(self, query, limit=5):
            return [{"name": query, "lat": 10.0, "lon": 20.0}]

    places = FakePlaces(error=RuntimeError("Provider offline"))

    monkeypatch.setattr(travel_apis, "geocoder", lambda: FakeGeocoder())
    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    try:
        travel_apis.resolve_airport_candidates("Any location")
    except travel_apis.AirportResolutionError as exc:
        assert "Provider offline" in str(exc)
    else:
        raise AssertionError("Provider failure was silently swallowed.")


def test_invalid_iata_input_is_not_treated_as_a_code(monkeypatch):
    class FakeGeocoder:
        def search(self, query, limit=5):
            return []

    places = FakePlaces()

    monkeypatch.setattr(travel_apis, "geocoder", lambda: FakeGeocoder())
    monkeypatch.setattr(travel_apis, "places_provider", lambda: places)

    assert travel_apis.resolve_airport_candidates("AB") == []
