from types import SimpleNamespace

from pydantic import BaseModel

from app.services.context.provider_links import sanitize_travel_payload, validate_provider_url
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


def test_booking_search_url_is_allowlisted_but_not_claimed_reachable():
    checked = validate_provider_url(
        "https://www.booking.com/searchresults.html?ss=Goa&checkin=2026-12-20&checkout=2026-12-23",
        artifact="hotels",
    )
    assert checked["status"] == "allowlisted_format_unverified"
    assert checked["link_kind"] == "search_handoff"
    assert checked["network_checked"] is False
    assert checked["reachable"] is None


def test_rejects_http_untrusted_hosts_credentials_and_nonstandard_ports():
    urls = [
        "http://www.booking.com/searchresults.html",
        "https://booking.com.attacker.example/searchresults.html",
        "https://booking.com@attacker.example/searchresults.html",
        "https://www.booking.com:8443/searchresults.html",
        "https://example.invalid/booking",
    ]
    for url in urls:
        assert validate_provider_url(url, artifact="hotels")["status"] == "rejected"


def test_uber_and_ola_handoffs_must_match_their_provider_domains():
    payload = sanitize_travel_payload("get_cab_links", {
        "type": "transport_links",
        "origin": "Airport",
        "destination": "Hotel",
        "links": {
            "uber": "https://m.uber.com/ul/?action=setPickup",
            "ola": "https://book.olacabs.com/?pickup_name=Airport",
            "fake": "https://example.invalid/ride",
        },
    })
    assert set(payload["links"]) == {"uber", "ola"}
    assert payload["links_validation"]["fake"]["status"] == "rejected"
    assert payload["link_validation_summary"]["booking_completed"] is False


def test_wrong_provider_host_is_rejected_even_when_domain_is_trusted():
    checked = validate_provider_url(
        "https://www.booking.com/searchresults.html",
        artifact="transfers",
        provider_id="uber",
    )
    assert checked["status"] == "rejected"


def test_invalid_candidate_booking_link_is_removed_and_reason_retained():
    payload = sanitize_travel_payload("search_hotels_stayapi", {
        "type": "hotel_list",
        "items": [{
            "name": "Test Hotel",
            "booking_url": "https://booking.com.attacker.example/hotel/test",
        }],
    })
    item = payload["items"][0]
    assert item["booking_url"] is None
    assert "not allowlisted" in item["booking_url_rejected_reason"]


def test_search_handoff_is_validated_and_labelled_as_search_not_booking():
    payload = sanitize_travel_payload("search_flights_real", {
        "type": "flight_list",
        "items": [],
        "search_url": "https://www.google.com/travel/flights?q=BHO+to+GOI",
        "live_inventory": False,
    })
    assert payload["search_url"] is not None
    assert payload["search_url_validation"]["status"] == "allowlisted_format_unverified"
    assert payload["search_url_validation"]["link_kind"] == "search_handoff"
    assert payload["link_validation_summary"]["reachable"] is None


def test_non_travel_payload_is_returned_unchanged():
    original = {"type": "document", "url": "https://example.invalid/file"}
    assert sanitize_travel_payload("answer_document", original) is original


class _Input(BaseModel):
    value: str


class _CabFixture(BaseTool):
    name = "get_cab_links"
    input_schema = _Input

    def execute(self, ctx, params):
        return ToolResult(True, "Handoff", {
            "type": "transport_links",
            "links": {"uber": "https://m.uber.com/ul/", "ola": "https://example.invalid/ola"},
        })


class _DB:
    def add(self, _value):
        pass
    def commit(self):
        pass
    def rollback(self):
        pass


def test_registry_dispatch_sanitizes_tool_results_before_returning_them():
    registry = ToolRegistry.__new__(ToolRegistry)
    registry._tools = {"get_cab_links": _CabFixture()}
    ctx = ToolContext(db=_DB(), user=SimpleNamespace(id=1))
    result = registry.dispatch(ctx, "get_cab_links", {"value": "fixture"})
    assert result.data["links"] == {"uber": "https://m.uber.com/ul/"}
    assert result.data["links_validation"]["ola"]["status"] == "rejected"
