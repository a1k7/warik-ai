from types import SimpleNamespace

from app.tools import food_tools
from app.tools.food_tools import DiscoverFoodInput, DiscoverFoodTool


def _context():
    return SimpleNamespace(db=None, user=None)


def test_food_discovery_uses_openstreetmap_without_geoapify_key(monkeypatch):
    monkeypatch.setattr(food_tools.settings, "geoapify_api_key", "")

    class Provider:
        def search(self, location, *, kind, limit, radius_m):
            assert location["name"] == "Delhi"
            assert kind == "restaurant"
            assert limit == 30
            assert radius_m == 15000
            return [{
                "name": "Test Restaurant",
                "address": "Connaught Place, Delhi",
                "lat": 28.6304,
                "lon": 77.2177,
                "category": "restaurant",
                "source": "OpenStreetMap",
            }]

    monkeypatch.setattr(food_tools, "places_provider", lambda: Provider())

    result = DiscoverFoodTool().execute(
        _context(),
        DiscoverFoodInput(location="Delhi", query="restaurant", budget=800),
    )

    assert result.success
    assert "OpenStreetMap-listed" in result.message
    assert result.data["items"][0]["name"] == "Test Restaurant"
    assert result.data["items"][0]["source"] == "OpenStreetMap"
    assert result.data["items"][0]["maps_url"].startswith(
        "https://www.openstreetmap.org/"
    )


def test_food_discovery_returns_graceful_error_when_overpass_fails(monkeypatch):
    monkeypatch.setattr(food_tools.settings, "geoapify_api_key", "")

    class Provider:
        def search(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(food_tools, "places_provider", lambda: Provider())

    result = DiscoverFoodTool().execute(
        _context(),
        DiscoverFoodInput(location="Delhi"),
    )

    assert not result.success
    assert "temporarily unavailable" in result.message
    assert "provider unavailable" not in result.message
    assert result.data["provider_status"] == "unavailable"


def test_food_discovery_reports_empty_openstreetmap_results(monkeypatch):
    class Provider:
        def search(self, *args, **kwargs):
            return []

    monkeypatch.setattr(food_tools, "places_provider", lambda: Provider())

    result = DiscoverFoodTool().execute(
        _context(),
        DiscoverFoodInput(location="Delhi"),
    )

    assert result.success
    assert result.data["items"] == []
    assert "No OpenStreetMap restaurant listings" in result.message
