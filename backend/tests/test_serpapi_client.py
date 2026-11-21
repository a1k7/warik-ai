from types import SimpleNamespace

import httpx
import pytest

from app.integrations.serpapi import client as serpapi


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    serpapi.clear_cache()
    monkeypatch.setattr(
        serpapi.settings,
        "serpapi_api_key",
        "test-secret-key",
    )
    yield
    serpapi.clear_cache()


def _success_payload(search_id="test-search"):
    return {
        "search_metadata": {
            "status": "Success",
            "id": search_id,
        },
        "organic_results": [{"title": "Example"}],
    }


def test_cache_key_does_not_depend_on_api_key():
    first = serpapi._cache_key({
        "engine": "google_flights",
        "api_key": "secret-one",
        "departure_id": "BLR",
    })
    second = serpapi._cache_key({
        "engine": "google_flights",
        "api_key": "secret-two",
        "departure_id": "BLR",
    })
    assert first == second


def test_successful_response_is_cached(monkeypatch):
    calls = {"count": 0}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            calls["count"] += 1
            return SimpleNamespace(
                is_error=False,
                json=lambda: _success_payload(),
            )

    monkeypatch.setattr(serpapi.httpx, "Client", FakeClient)

    api = serpapi.SerpApiClient(cache_ttl_seconds=60)
    params = {"engine": "google_flights", "departure_id": "BLR"}

    first = api.search(params)
    second = api.search(params)

    assert first == second
    assert calls["count"] == 1


def test_cached_payload_is_returned_as_a_copy(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return SimpleNamespace(
                is_error=False,
                json=lambda: _success_payload(),
            )

    monkeypatch.setattr(serpapi.httpx, "Client", FakeClient)

    api = serpapi.SerpApiClient(cache_ttl_seconds=60)
    params = {"engine": "google_flights"}

    first = api.search(params)
    first["organic_results"].clear()

    second = api.search(params)
    assert second["organic_results"] == [{"title": "Example"}]


def test_provider_error_is_redacted():
    response = SimpleNamespace(
        is_error=False,
        json=lambda: {
            "search_metadata": {"status": "Error"},
            "error": "Invalid key test-secret-key",
        },
    )

    with pytest.raises(serpapi.SerpApiError) as exc:
        serpapi._parse_response(response)

    assert "test-secret-key" not in str(exc.value)
    assert "[redacted]" in str(exc.value)


def test_http_error_does_not_expose_response_body():
    response = SimpleNamespace(is_error=True, status_code=429)

    with pytest.raises(serpapi.SerpApiError) as exc:
        serpapi._parse_response(response)

    assert "429" in str(exc.value)
    assert "test-secret-key" not in str(exc.value)


def test_missing_api_key_fails_before_network(monkeypatch):
    monkeypatch.setattr(serpapi.settings, "serpapi_api_key", "")

    with pytest.raises(serpapi.SerpApiError, match="not configured"):
        serpapi.SerpApiClient().search({"engine": "google_flights"})
