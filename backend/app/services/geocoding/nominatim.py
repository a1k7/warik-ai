"""Nominatim geocoding adapter with conservative public-service throttling."""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from typing import Any

import httpx

DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/search"
_LOCK = threading.Lock()
_LAST_REQUEST = 0.0

def _throttle(min_interval: float) -> None:
    global _LAST_REQUEST
    with _LOCK:
        now = time.monotonic()
        wait = min_interval - (now - _LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST = time.monotonic()

class NominatimProvider:
    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        user_agent: str = "WarikAI/1.0 (travel planning; contact: configure WARIK_GEO_USER_AGENT)",
        timeout: float = 12.0,
        min_interval: float = 1.1,
    ) -> None:
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval = max(1.0, min_interval)

    @lru_cache(maxsize=512)
    def _cached_search(self, query: str, limit: int) -> tuple[dict, ...]:
        _throttle(self.min_interval)
        headers = {"User-Agent": self.user_agent}
        params = {"q": query, "format": "jsonv2", "addressdetails": 1, "limit": limit, "dedupe": 1}
        with httpx.Client(timeout=self.timeout, headers=headers) as client:
            response = client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
        normalized = []
        for item in payload if isinstance(payload, list) else []:
            try:
                lat, lon = float(item["lat"]), float(item["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            address = item.get("address") or {}
            display = str(item.get("display_name") or query)
            name = (
                address.get("city") or address.get("town") or address.get("village")
                or address.get("municipality") or address.get("county")
                or item.get("name") or display.split(",")[0]
            )
            normalized.append({
                "name": str(name).strip(),
                "state": str(address.get("state") or address.get("region") or "").strip(),
                "country": str(address.get("country") or "").strip(),
                "lat": lat,
                "lon": lon,
                "type": str(item.get("type") or item.get("class") or "location"),
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "display_name": display,
                "importance": float(item.get("importance") or 0),
                "source": "OpenStreetMap Nominatim",
            })
        return tuple(normalized)

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        query = " ".join(str(query).strip().split())
        if not query:
            return []
        return [dict(item) for item in self._cached_search(query, limit)]
