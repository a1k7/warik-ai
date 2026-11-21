"""Shared, quota-conscious SerpApi transport for Warik AI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from copy import deepcopy
from typing import Any

import httpx

from app.core.config import settings


SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
DEFAULT_CACHE_TTL_SECONDS = 900
MAX_CACHE_ENTRIES = 256


class SerpApiError(RuntimeError):
    """Safe provider error that never exposes the API key."""


_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.RLock()


def _cache_key(params: dict[str, Any]) -> str:
    """Build a stable cache key without storing the API key."""
    safe_params = {
        str(key): value
        for key, value in params.items()
        if key != "api_key"
    }
    encoded = json.dumps(
        safe_params,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at <= now:
            _cache.pop(key, None)
            return None
        return deepcopy(payload)


def _cache_put(
    key: str,
    payload: dict[str, Any],
    ttl_seconds: int,
) -> None:
    if ttl_seconds <= 0:
        return

    now = time.monotonic()
    with _cache_lock:
        expired = [
            cache_key
            for cache_key, (expires_at, _) in _cache.items()
            if expires_at <= now
        ]
        for cache_key in expired:
            _cache.pop(cache_key, None)

        while len(_cache) >= MAX_CACHE_ENTRIES:
            oldest_key = next(iter(_cache))
            _cache.pop(oldest_key, None)

        _cache[key] = (now + ttl_seconds, deepcopy(payload))


def clear_cache() -> None:
    """Clear the in-process cache. Intended for tests and maintenance."""
    with _cache_lock:
        _cache.clear()


def _prepare_params(params: dict[str, Any]) -> dict[str, Any]:
    api_key = settings.serpapi_api_key.strip()
    if not api_key:
        raise SerpApiError(
            "SerpApi is not configured. Add SERPAPI_API_KEY to backend/.env."
        )

    prepared = dict(params)
    prepared["api_key"] = api_key
    return prepared


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise SerpApiError(
            f"SerpApi returned HTTP {response.status_code}. "
            "Check account quota, credentials, and provider status."
        )

    try:
        payload = response.json()
    except ValueError:
        raise SerpApiError(
            "SerpApi returned an invalid JSON response."
        ) from None

    if not isinstance(payload, dict):
        raise SerpApiError("SerpApi returned an unexpected response format.")

    metadata = payload.get("search_metadata") or {}
    if metadata.get("status") != "Success":
        message = str(
            payload.get("error")
            or f"Provider search status: {metadata.get('status', 'unknown')}"
        )
        api_key = settings.serpapi_api_key.strip()
        if api_key:
            message = message.replace(api_key, "[redacted]")
        raise SerpApiError(message[:300])

    return payload


class SerpApiClient:
    """Shared sync/async SerpApi client with successful-response caching."""

    def __init__(
        self,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.serpapi_timeout_seconds
        )
        self.cache_ttl_seconds = cache_ttl_seconds

    def search(
        self,
        params: dict[str, Any],
        *,
        cache_ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        prepared = _prepare_params(params)
        key = _cache_key(prepared)

        cached = _cache_get(key)
        if cached is not None:
            return cached

        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(SERPAPI_ENDPOINT, params=prepared)
        except httpx.RequestError as exc:
            raise SerpApiError(
                f"SerpApi network request failed ({type(exc).__name__})."
            ) from None

        payload = _parse_response(response)
        ttl = (
            self.cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        _cache_put(key, payload, ttl)
        return payload

    async def asearch(
        self,
        params: dict[str, Any],
        *,
        cache_ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        prepared = _prepare_params(params)
        key = _cache_key(prepared)

        cached = _cache_get(key)
        if cached is not None:
            return cached

        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    SERPAPI_ENDPOINT,
                    params=prepared,
                )
        except httpx.RequestError as exc:
            raise SerpApiError(
                f"SerpApi network request failed ({type(exc).__name__})."
            ) from None

        payload = _parse_response(response)
        ttl = (
            self.cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        _cache_put(key, payload, ttl)
        return payload


serpapi_client = SerpApiClient()
