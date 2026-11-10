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
