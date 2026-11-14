"""Efficient OpenStreetMap Overpass API adapter for nearby places.

Uses compact ``nwr`` selectors, bounded endpoint fallback, successful-result
caching, input validation, and the existing Warik AI place-record schema.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"

# Public community-operated endpoints. Availability and capacity vary.
FALLBACK_ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# Compact selectors reduce repeated node/way/relation scans. Keep categories
# explicit so the adapter does not return every historic or leisure object.
ATTRACTION_FILTER = (
    'nwr["tourism"~"^(attraction|museum|gallery|zoo|theme_park|viewpoint)$"]',
    'nwr["historic"]',
    'nwr["leisure"~"^(park|nature_reserve)$"]',
)

RESTAURANT_FILTER = (
    'nwr["amenity"~"^(restaurant|cafe|fast_food|food_court)$"]',
)

RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class OverpassProvider:
    """Search OpenStreetMap for nearby attractions and restaurants.

    Public Overpass servers are best-effort community infrastructure. This
    adapter uses compact queries, bounded retries, endpoint fallback, and a
    small in-memory TTL cache. It raises provider errors rather than silently
    representing an outage as an empty list.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 60.0,
        user_agent: str = "WarikAI/1.0 (travel planning)",
        fallback_endpoints: tuple[str, ...] | None = None,
        max_retries: int = 2,
        query_timeout: int = 40,
        cache_ttl_seconds: int = 900,
        cache_max_entries: int = 256,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = max(1.0, float(timeout))
        self.user_agent = user_agent
        self.max_retries = max(0, int(max_retries))
        self.query_timeout = max(1, int(query_timeout))
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.cache_max_entries = max(1, int(cache_max_entries))
        self._cache: dict[tuple[Any, ...], tuple[float, list[dict]]] = {}

        fallbacks = (
            FALLBACK_ENDPOINTS
            if fallback_endpoints is None
            else fallback_endpoints
        )
        self.endpoints = list(
            dict.fromkeys(
                candidate.strip()
                for candidate in (endpoint, *fallbacks)
                if candidate and candidate.strip()
            )
        )

    @staticmethod
    def _validate_location(location: dict) -> tuple[float, float]:
        """Validate and normalize geographic coordinates."""
        try:
            lat = float(location["lat"])
            lon = float(location["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Location must contain valid numeric 'lat' and 'lon' values."
            ) from exc

        if not -90 <= lat <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        if not -180 <= lon <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        return lat, lon

    @staticmethod
    def _build_query(
        lat: float,
        lon: float,
        filters: tuple[str, ...],
        limit: int,
        radius_m: int,
        query_timeout: int,
    ) -> str:
        """Build a compact Overpass QL query for one POI category."""
        statements = "\n".join(
            f"{selector}(around:{radius_m},{lat},{lon});"
            for selector in filters
        )
        return (
            f"[out:json][timeout:{query_timeout}];\n"
            f"({statements});\n"
            f"out center tags {limit};"
        )

    def _request(self, query: str) -> dict[str, Any]:
        """Execute a request with bounded retries and endpoint fallback."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        total_attempts = min(len(self.endpoints), self.max_retries + 1)
        last_error: Exception | None = None

        for attempt, endpoint in enumerate(self.endpoints[:total_attempts]):
            try:
                logger.info(
                    "Overpass request attempt %s/%s using %s",
                    attempt + 1,
                    total_attempts,
                    endpoint,
                )
                with httpx.Client(
                    timeout=httpx.Timeout(self.timeout),
                    headers=headers,
                    follow_redirects=True,
                ) as client:
                    response = client.post(endpoint, data={"data": query})

                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(
                        "Overpass returned an unexpected response format."
                    )

                # Overpass can return an HTTP 200 JSON body containing a
                # remark when it could not complete the query.
                remark = payload.get("remark")
                if remark:
                    raise RuntimeError(f"Overpass query was not completed: {remark}")

                return payload

            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status not in RETRYABLE_STATUS_CODES:
                    raise
                logger.warning(
                    "Overpass endpoint returned HTTP %s: %s", status, endpoint
                )
            except (httpx.TransportError, RuntimeError, ValueError) as exc:
                last_error = exc
                logger.warning("Overpass request failed at %s: %s", endpoint, exc)

        if last_error is not None:
            raise last_error
        raise RuntimeError("No Overpass endpoint was available.")

    @staticmethod
    def _parse_results(
        payload: dict[str, Any], location: dict, limit: int
    ) -> list[dict]:
        """Normalize raw Overpass elements into Warik AI place records."""
        results: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = str(tags.get("name") or tags.get("name:en") or "").strip()
            if len(name) < 3:
                continue

            osm_type = element.get("type")
            osm_id = element.get("id")
            if osm_type is not None and osm_id is not None:
                identity = (str(osm_type), str(osm_id))
                if identity in seen:
                    continue
                seen.add(identity)

            center = element.get("center") or {}
            try:
                item_lat = float(element.get("lat", center.get("lat")))
                item_lon = float(element.get("lon", center.get("lon")))
            except (TypeError, ValueError):
                continue

            if not -90 <= item_lat <= 90 or not -180 <= item_lon <= 180:
                continue

            address_parts = (
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city"),
                tags.get("addr:town"),
                tags.get("addr:country"),
            )
            address = ", ".join(str(part) for part in address_parts if part)

            fee = str(tags.get("fee", "")).strip().lower()
            entry_fee = (
                "Free" if fee in {"no", "false", "0"} else tags.get("charge")
            )
            category = (
                tags.get("tourism")
                or tags.get("historic")
                or tags.get("amenity")
                or tags.get("leisure")
            )
            dietary_tags = {
                key: value
                for key, value in tags.items()
                if key.startswith("diet:") and value not in (None, "")
            }

            results.append(
                {
                    "name": name,
                    "address": address,
                    "city": location.get("name", ""),
                    "lat": item_lat,
                    "lon": item_lon,
                    "category": category,
                    "dietary_tags": dietary_tags,
                    "opening_hours": tags.get("opening_hours"),
                    "entry_fee": entry_fee,
                    "image_url": None,
                    "wikimedia_commons": tags.get("wikimedia_commons"),
                    "wikipedia": tags.get("wikipedia"),
                    "wikidata": tags.get("wikidata"),
                    "source": "OpenStreetMap",
                    "osm_type": osm_type,
                    "osm_id": osm_id,
                }
            )
            if len(results) >= limit:
                break

        return results

    def _cache_get(self, key: tuple[Any, ...]) -> list[dict] | None:
        if self.cache_ttl_seconds <= 0:
            return None
        cached = self._cache.get(key)
        if cached is None:
            return None
        expires_at, value = cached
        if time.monotonic() >= expires_at:
            self._cache.pop(key, None)
            return None
        # Return copies so callers cannot mutate the cached records.
        return [dict(item) for item in value]

    def _cache_put(self, key: tuple[Any, ...], value: list[dict]) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        if len(self._cache) >= self.cache_max_entries:
            oldest_key = min(self._cache, key=lambda item: self._cache[item][0])
            self._cache.pop(oldest_key, None)
        self._cache[key] = (
            time.monotonic() + self.cache_ttl_seconds,
            [dict(item) for item in value],
        )

    def search(
        self,
        location: dict,
        *,
        kind: str,
        limit: int = 20,
        radius_m: int = 15000,
    ) -> list[dict]:
        """Find nearby attractions or restaurants.

        Args:
            location: Dictionary containing lat, lon and optionally name.
            kind: Either 'attraction' or 'restaurant'.
            limit: Maximum number of returned places (1-100).
            radius_m: Search radius in metres (100-50000).

        Returns:
            Normalized place dictionaries. Provider outages raise an error;
            they are never silently represented as an empty result list.
        """
        if kind not in {"attraction", "restaurant"}:
            raise ValueError("kind must be either 'attraction' or 'restaurant'.")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer.")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if not isinstance(radius_m, int) or isinstance(radius_m, bool):
            raise ValueError("radius_m must be an integer.")
        if not 100 <= radius_m <= 50000:
            raise ValueError("radius_m must be between 100 and 50000 metres.")

        lat, lon = self._validate_location(location)
        filters = RESTAURANT_FILTER if kind == "restaurant" else ATTRACTION_FILTER
        cache_key = (
            kind,
            round(lat, 5),
            round(lon, 5),
            str(location.get("name", "")),
            limit,
            radius_m,
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Overpass cache hit for %s at %s,%s", kind, lat, lon)
            return cached

        query = self._build_query(
            lat=lat,
            lon=lon,
            filters=filters,
            limit=limit,
            radius_m=radius_m,
            query_timeout=self.query_timeout,
        )
        payload = self._request(query)
        results = self._parse_results(payload, location, limit)
        self._cache_put(cache_key, results)
        return results


    def search_airports(
        self,
        location: dict,
        *,
        limit: int = 100,
        radius_m: int = 50000,
    ) -> list[dict]:
        """Discover nearby airports from OpenStreetMap records."""
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer.")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if not isinstance(radius_m, int) or isinstance(radius_m, bool):
            raise ValueError("radius_m must be an integer.")
        if not 100 <= radius_m <= 100000:
            raise ValueError("radius_m must be between 100 and 100000 metres.")

        lat, lon = self._validate_location(location)
        cache_key = (
            "airport",
            round(lat, 5),
            round(lon, 5),
            limit,
            radius_m,
        )

        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        query = self._build_query(
            lat=lat,
            lon=lon,
            filters=('nwr["aeroway"="aerodrome"]',),
            limit=limit,
            radius_m=radius_m,
            query_timeout=self.query_timeout,
        )

        payload = self._request(query)
        results = []
        seen = set()

        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            center = element.get("center") or {}

            try:
                airport_lat = float(element.get("lat", center.get("lat")))
                airport_lon = float(element.get("lon", center.get("lon")))
            except (TypeError, ValueError):
                continue

            if not -90 <= airport_lat <= 90:
                continue
            if not -180 <= airport_lon <= 180:
                continue

            identity = (element.get("type"), element.get("id"))
            if identity in seen:
                continue
            seen.add(identity)

            results.append({
                "name": str(
                    tags.get("name")
                    or tags.get("name:en")
                    or tags.get("iata")
                    or "Unnamed airport"
                ).strip(),
                "iata": str(tags.get("iata") or "").strip().upper(),
                "icao": str(tags.get("icao") or "").strip().upper(),
                "lat": airport_lat,
                "lon": airport_lon,
                "source": "OpenStreetMap",
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
            })

        self._cache_put(cache_key, results)
        return results

    def search_airports_by_iata(
        self,
        iata: str,
        *,
        limit: int = 10,
    ) -> list[dict]:
        """Find airport records with an exact IATA tag."""
        code = str(iata or "").strip().upper()

        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("A valid three-letter IATA code is required.")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer.")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")

        cache_key = ("airport_iata", code, limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        query = (
            f'[out:json][timeout:{self.query_timeout}];\n'
            f'(nwr["aeroway"="aerodrome"]["iata"="{code}"];);\n'
            f'out center tags {limit};'
        )

        payload = self._request(query)
        results = []
        seen = set()

        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            record_code = str(tags.get("iata") or "").strip().upper()

            if record_code != code:
                continue

            center = element.get("center") or {}
            try:
                lat = float(element.get("lat", center.get("lat")))
                lon = float(element.get("lon", center.get("lon")))
            except (TypeError, ValueError):
                continue

            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                continue

            identity = (element.get("type"), element.get("id"))
            if identity in seen:
                continue
            seen.add(identity)

            results.append({
                "name": str(
                    tags.get("name")
                    or tags.get("name:en")
                    or "Unnamed airport"
                ).strip(),
                "iata": record_code,
                "icao": str(tags.get("icao") or "").strip().upper(),
                "lat": lat,
                "lon": lon,
                "source": "OpenStreetMap",
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
            })

            if len(results) >= limit:
                break

        self._cache_put(cache_key, results)
        return results
