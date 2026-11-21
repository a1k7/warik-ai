import httpx
import pytest

from app.integrations.stayapi.client import StayAPIClient, StayAPIError


def test_stayapi_resolves_destination_then_searches_and_normalizes(monkeypatch):
    calls = []

    def fake_get(url, *, params, headers, timeout, follow_redirects):
        calls.append((url, params, headers))
        if url.endswith("/booking/destinations/lookup"):
            payload = {
                "success": True,
                "dest_id": -123,
                "dest_type": "CITY",
                "normalized_query": "Goa, India",
                "suggestions": [],
            }
        else:
            payload = {
                "success": True,
                "data": [{
                    "hotel_id": 77,
                    "hotel_name": "Test Stay",
                    "url": "https://www.booking.com/hotel/in/test.html",
                    "min_total_price": 6000,
                    "currency_code": "INR",
                    "review_score": 8.8,
                    "review_count": 100,
                    "star_rating": 4,
                    "is_free_cancellable": 1,
                    "checkin": "2026-12-10",
                    "checkout": "2026-12-13",
                }],
                "retrieved_at": "2026-11-19T12:00:00Z",
            }
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.integrations.stayapi.client.httpx.get", fake_get)
    result = StayAPIClient("test-key").search_hotels(
        city="Goa", check_in="2026-12-10", check_out="2026-12-13", adults=2
    )

    assert len(calls) == 2
    assert calls[1][1]["dest_id"] == "-123"
    assert calls[1][1]["currency"] == "INR"
    assert result["provider"] == "stayapi_booking"
    assert result["live_inventory"] is True
    assert result["items"][0]["total_stay_amount"] == 6000
    assert result["items"][0]["price_per_night_amount"] == 2000
    assert result["items"][0]["price_per_night"] == "INR 2,000.00"
    assert result["items"][0]["total_inr"] == 6000


def test_stayapi_rejects_invalid_dates_before_network(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("network must not be called")
    monkeypatch.setattr("app.integrations.stayapi.client.httpx.get", unexpected)
    with pytest.raises(ValueError, match="Check-out must be after"):
        StayAPIClient("test-key").search_hotels(
            city="Goa", check_in="2026-12-12", check_out="2026-12-12"
        )


def test_stayapi_rejects_missing_api_key():
    with pytest.raises(StayAPIError, match="not configured"):
        StayAPIClient("")


def test_stayapi_sanitizes_http_errors(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(403, text="secret details should not escape", request=httpx.Request("GET", url))
    monkeypatch.setattr("app.integrations.stayapi.client.httpx.get", fake_get)
    with pytest.raises(StayAPIError) as exc:
        StayAPIClient("test-key").search_hotels(
            city="Goa", check_in="2026-12-10", check_out="2026-12-12"
        )
    assert "secret details" not in str(exc.value)
