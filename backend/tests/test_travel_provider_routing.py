"""Provider routing tests; all network and CLI boundaries are mocked."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.tools.base import ToolContext
from app.tools.provider_selector import ProviderSelector
from app.tools.registry import ToolRegistry
from app.tools.travel_apis import (
    FlightInput,
    HotelInput,
    RealFlightSearchTool,
    StayApiHotelTool,
)


class _Registry:
    def __init__(self, tool):
        self.tool = tool
    def list_tools(self):
        return [self.tool.name]
    def get(self, name):
        return self.tool if name == self.tool.name else None


def _ctx():
    return ToolContext(db=SimpleNamespace(rollback=lambda: None), user=SimpleNamespace(id=1))


def test_provider_selector_uses_cli_when_adapter_api_key_is_not_authenticated():
    class Tool:
        name = "sample"
        capability = "travel"
        execution_status = "available"
        requires_auth = False
        supported_operations = ("search",)
        provider_adapters = (
            {"provider_id": "paid_api", "requires_auth": True},
            {"provider_id": "trvl_cli"},
        )
    selection = ProviderSelector(_Registry(Tool())).select(
        capability="travel", operation="search", tool_name="sample"
    )
    assert selection.available
    assert selection.selected.provider_id == "trvl_cli"
    assert any(item.provider_id == "paid_api" for item in selection.rejected)


def test_provider_selector_allows_authenticated_adapter():
    class Tool:
        name = "sample"
        capability = "travel"
        execution_status = "available"
        requires_auth = False
        supported_operations = ("search",)
        provider_adapters = (
            {"provider_id": "paid_api", "requires_auth": True},
            {"provider_id": "trvl_cli"},
        )
    selection = ProviderSelector(_Registry(Tool())).select(
        capability="travel", operation="search", tool_name="sample",
        authenticated_providers=("paid_api",),
    )
    assert selection.available
    assert selection.selected.provider_id == "paid_api"


def test_hotel_stayapi_selection_does_not_call_cli(monkeypatch):
    from app.integrations.stayapi.client import StayAPIClient
    monkeypatch.setattr(settings, "stayapi_key", "test-stayapi-key")
    calls = []
    def fake_search(self, **kwargs):
        calls.append(kwargs)
        return {"items": [{"name": "StayAPI Fixture Hotel", "total_stay_amount": 12000, "currency": "INR", "nights": 2}], "retrieved_at": "2026-11-19T00:00:00+00:00"}
    monkeypatch.setattr(StayAPIClient, "search_hotels", fake_search)
    monkeypatch.setattr("app.tools.travel_apis.shutil.which", lambda _: (_ for _ in ()).throw(AssertionError("CLI must not run")))
    tool = StayApiHotelTool()
    result = tool.execute_for_provider(
        _ctx(), HotelInput(city="Goa", check_in="2026-12-20", check_out="2026-12-22", travellers=2),
        "stayapi_booking",
    )
    assert result.success is True
    assert result.data["provider"] == "stayapi_booking"
    assert len(calls) == 1


def test_hotel_trvl_selection_skips_stayapi_even_when_key_exists(monkeypatch):
    from app.integrations.stayapi.client import StayAPIClient
    monkeypatch.setattr(settings, "stayapi_key", "test-stayapi-key")
    monkeypatch.setattr(StayAPIClient, "search_hotels", lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("StayAPI must not run")))
    payload = {"hotels": [{"name": "TRVL Fixture Hotel", "price": 5000, "currency": "INR"}]}
    monkeypatch.setattr("app.tools.travel_apis.shutil.which", lambda _: "/opt/homebrew/bin/trvl")
    monkeypatch.setattr("app.tools.travel_apis.subprocess.run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0))
    tool = StayApiHotelTool()
    result = tool.execute_for_provider(
        _ctx(), HotelInput(city="Goa", check_in="2026-12-20", check_out="2026-12-22", travellers=2),
        "trvl_cli",
    )
    assert result.success is True
    assert result.data["provider"] == "trvl_cli"
    assert result.data["items"][0]["name"] == "TRVL Fixture Hotel"
    assert result.data["live_inventory"] is True


def test_flight_serpapi_selection_never_falls_back_to_cli(monkeypatch):
    import app.tools.travel_apis as travel
    monkeypatch.setattr(travel, "resolve_airport_candidates", lambda city: [{"iata": "BHO" if city == "Bhopal" else "DEL", "name": city}])
    monkeypatch.setattr(travel.serpapi_client, "search", lambda params: {"fixture": True})
    monkeypatch.setattr(travel, "_normalise_serpapi_flights", lambda *a: ([{"price": "₹5,000", "price_amount": 5000, "currency": "INR", "segments": [{"origin": "BHO", "destination": "DEL", "departure": "2026-12-20 08:00", "arrival": "2026-12-20 10:00"}]}], "https://example.invalid/flights"))
    monkeypatch.setattr(travel.shutil, "which", lambda _: (_ for _ in ()).throw(AssertionError("CLI must not run")))
    tool = RealFlightSearchTool()
    result = tool.execute_for_provider(
        _ctx(), FlightInput(origin="Bhopal", destination="Delhi", date="2026-12-20", adults=1),
        "serpapi_google_flights",
    )
    assert result.success is True
    assert result.data["provider"] == "serpapi_google_flights"


def test_flight_trvl_selection_skips_serpapi(monkeypatch):
    import app.tools.travel_apis as travel
    monkeypatch.setattr(travel, "resolve_airport_candidates", lambda city: [{"iata": "BHO" if city == "Bhopal" else "DEL", "name": city}])
    monkeypatch.setattr(travel.serpapi_client, "search", lambda params: (_ for _ in ()).throw(AssertionError("SerpApi must not run")))
    cli_payload = {"flights": [{"price": 5000, "currency": "INR", "legs": [{"departure_airport": {"code": "BHO"}, "arrival_airport": {"code": "DEL"}, "departure_time": "2026-12-20T08:00", "arrival_time": "2026-12-20T10:00"}]}]}
    monkeypatch.setattr(travel.shutil, "which", lambda _: "/opt/homebrew/bin/trvl")
    monkeypatch.setattr(travel.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(cli_payload), stderr="", returncode=0))
    tool = RealFlightSearchTool()
    result = tool.execute_for_provider(
        _ctx(), FlightInput(origin="Bhopal", destination="Delhi", date="2026-12-20", adults=1),
        "trvl_cli",
    )
    assert result.success is True
    assert result.data["provider"] == "trvl_cli"
    assert result.data["items"]
