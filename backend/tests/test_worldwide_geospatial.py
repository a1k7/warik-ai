from unittest.mock import Mock
import httpx

from app.services.geocoding.nominatim import NominatimProvider
from app.services.places.overpass import OverpassProvider
from app.tools import trip_tools


def test_nominatim_normalizes_global_place(monkeypatch):
    provider = NominatimProvider(user_agent="WarikAI-test", min_interval=1.0)
    monkeypatch.setattr("app.services.geocoding.nominatim._throttle", lambda _: None)

    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{
                "lat": "48.8566", "lon": "2.3522", "name": "Paris",
                "type": "city", "importance": 0.9,
                "display_name": "Paris, Île-de-France, France",
                "address": {"city": "Paris", "state": "Île-de-France", "country": "France"},
            }]
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return Response()

    monkeypatch.setattr("app.services.geocoding.nominatim.httpx.Client", Client)
    result = provider.search("Paris, France")
    assert result[0]["name"] == "Paris"
    assert result[0]["country"] == "France"
    assert result[0]["lat"] == 48.8566


def test_overpass_normalizes_named_poi(monkeypatch):
    provider = OverpassProvider()
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"elements": [{
                "type": "node", "id": 123, "lat": 48.8584, "lon": 2.2945,
                "tags": {"name": "Eiffel Tower", "tourism": "attraction", "wikidata": "Q243"},
            }]}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr("app.services.places.overpass.httpx.Client", Client)
    result = provider.search({"name": "Paris", "lat": 48.85, "lon": 2.35},
                             kind="attraction", limit=10, radius_m=15000)
    assert result[0]["name"] == "Eiffel Tower"
    assert result[0]["source"] == "OpenStreetMap"


def test_destination_parser_preserves_admin_commas(monkeypatch):
    monkeypatch.setattr(trip_tools, "_geocode_place", lambda query: {
        "name": "Jaipur", "state": "Rajasthan", "country": "India",
        "lat": 26.9, "lon": 75.8, "type": "location"
    } if query == "Jaipur, Rajasthan, India" else None)
    locations, error = trip_tools._geocode_destination("Jaipur, Rajasthan, India")
    assert error is None
    assert len(locations) == 1
    assert locations[0]["name"] == "Jaipur"


def test_destination_parser_supports_explicit_multi_stop_route(monkeypatch):
    def fake(query):
        if query in {"Kochi", "Munnar"}:
            return {"name": query, "lat": 10.0, "lon": 76.0, "type": "location"}
        return None
    monkeypatch.setattr(trip_tools, "_geocode_place", fake)
    locations, error = trip_tools._geocode_destination("Kochi to Munnar")
    assert error is None
    assert [item["name"] for item in locations] == ["Kochi", "Munnar"]


def test_destination_parser_does_not_treat_traveller_context_as_location(monkeypatch):
    monkeypatch.setattr(trip_tools, "_geocode_place", lambda query: None)
    locations, error = trip_tools._geocode_destination("Jaipur for 2 people")
    assert locations == []
    assert "couldn't verify" in error.lower()


def test_generated_place_descriptions_do_not_invent_attraction_facts():
    descriptions = trip_tools._generate_descriptions(
        ["Example Monument", "Example Museum"],
        "Paris",
    )

    assert set(descriptions) == {"Example Monument", "Example Museum"}
    assert all("listed in Paris" in value for value in descriptions.values())
    assert all("Confirm visitor access" in value for value in descriptions.values())
    assert all("popular attraction" not in value.lower() for value in descriptions.values())


def test_activity_verification_does_not_overstate_osm_evidence(monkeypatch):
    monkeypatch.setattr(
        trip_tools,
        "_fetch_commons_image",
        lambda *args, **kwargs: {},
    )

    activity = trip_tools._build_activity(
        {
            "name": "Example Monument",
            "city": "Paris",
            "lat": 48.8584,
            "lon": 2.2945,
            "category": "tourism",
            "source": "OpenStreetMap",
        },
        "morning",
        "09:00",
        "A place listed in Paris.",
    )

    assert activity.verification["source_record_found"] is True
    assert activity.verification["coordinates_available"] is True
    assert activity.verification["category_tag_present"] is True
    assert activity.verification["tourism_suitability_verified"] is False
    assert activity.verification["hours_verified"] is False
    assert activity.verification["price_verified"] is False


def test_geocode_place_uses_nominatim_when_geoapify_key_missing(monkeypatch):
    monkeypatch.setattr(trip_tools.settings, "geoapify_api_key", "")

    class FakeGeocoder:
        def search(self, query, limit=5):
            assert query == "Paris, France"
            return [{
                "name": "Paris",
                "state": "Île-de-France",
                "country": "France",
                "lat": 48.8566,
                "lon": 2.3522,
                "type": "city",
                "source": "OpenStreetMap Nominatim",
            }]

    monkeypatch.setattr(trip_tools, "geocoder", lambda: FakeGeocoder())

    result = trip_tools._geocode_place("Paris, France")

    assert result["name"] == "Paris"
    assert result["country"] == "France"
    assert result["source"] == "OpenStreetMap Nominatim"


def test_geocode_place_rejects_nominatim_poi_as_city(monkeypatch):
    monkeypatch.setattr(trip_tools.settings, "geoapify_api_key", "")

    class FakeGeocoder:
        def search(self, query, limit=5):
            return [{
                "name": "Paris Cafe",
                "state": "",
                "country": "France",
                "lat": 48.8566,
                "lon": 2.3522,
                "type": "cafe",
            }]

    monkeypatch.setattr(trip_tools, "geocoder", lambda: FakeGeocoder())

    assert trip_tools._geocode_place("Paris Cafe") is None


def test_fetch_places_uses_overpass_when_geoapify_key_missing(monkeypatch):
    monkeypatch.setattr(trip_tools.settings, "geoapify_api_key", "")

    class FakePlacesProvider:
        def search(self, city, *, kind, limit, radius_m):
            assert city["name"] == "Paris"
            assert kind == "attraction"
            assert limit == 10
            assert radius_m == 15000
            return [{
                "name": "Eiffel Tower",
                "city": "Paris",
                "lat": 48.8584,
                "lon": 2.2945,
                "category": "attraction",
                "source": "OpenStreetMap",
            }]

    monkeypatch.setattr(trip_tools, "places_provider", lambda: FakePlacesProvider())

    results = trip_tools._fetch_places(
        {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
        trip_tools.ATTRACTION_CATEGORIES,
        10,
        15000,
    )

    assert len(results) == 1
    assert results[0]["name"] == "Eiffel Tower"
    assert results[0]["source"] == "OpenStreetMap"


def test_fetch_places_uses_overpass_for_restaurant_categories(monkeypatch):
    monkeypatch.setattr(trip_tools.settings, "geoapify_api_key", "")

    class FakePlacesProvider:
        def search(self, city, *, kind, limit, radius_m):
            assert kind == "restaurant"
            return [{"name": "Example Cafe", "source": "OpenStreetMap"}]

    monkeypatch.setattr(trip_tools, "places_provider", lambda: FakePlacesProvider())

    results = trip_tools._fetch_places(
        {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
        trip_tools.RESTAURANT_CATEGORIES,
        5,
        10000,
    )

    assert results[0]["name"] == "Example Cafe"


def test_overpass_preserves_all_explicit_dietary_tags():
    from app.services.places.overpass import OverpassProvider

    payload = {
        "elements": [{
            "type": "node",
            "id": 987654,
            "lat": 28.6139,
            "lon": 77.2090,
            "tags": {
                "name": "Dietary Test Cafe",
                "amenity": "restaurant",
                "diet:vegetarian": "yes",
                "diet:vegan": "only",
                "diet:custom-tag": "limited",
                "opening_hours": "Mo-Su 09:00-22:00",
            },
        }]
    }

    result = OverpassProvider._parse_results(
        payload,
        {"name": "Delhi"},
        10,
    )

    assert len(result) == 1
    assert result[0]["dietary_tags"] == {
        "diet:vegetarian": "yes",
        "diet:vegan": "only",
        "diet:custom-tag": "limited",
    }


def test_overpass_uses_only_configured_attempt_limit(monkeypatch):
    import httpx
    from app.services.places.overpass import OverpassProvider

    calls = []

    def handler(request):
        calls.append(str(request.url))
        raise httpx.ConnectError("network unavailable")

    provider = OverpassProvider(
        endpoint="https://primary.example/api",
        fallback_endpoints=(
            "https://fallback.example/api",
            "https://third.example/api",
        ),
        timeout=1,
        max_retries=1,
    )

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=transport,
            **kwargs,
        ),
    )

    import pytest
    with pytest.raises(httpx.ConnectError):
        provider._request("[out:json];out;")

    assert calls == [
        "https://primary.example/api",
        "https://fallback.example/api",
    ]


def test_overpass_falls_back_after_invalid_json(monkeypatch):
    import httpx
    from app.services.places.overpass import OverpassProvider

    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(200, text="not-json")
        return httpx.Response(200, json={"elements": []})

    provider = OverpassProvider(
        endpoint="https://primary.example/api",
        fallback_endpoints=("https://fallback.example/api",),
        timeout=1,
        max_retries=1,
    )

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=transport,
            **kwargs,
        ),
    )

    result = provider._request("[out:json];out;")

    assert result == {"elements": []}
    assert len(calls) == 2
