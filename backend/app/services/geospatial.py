"""Shared provider instances and normalized geospatial access."""
from functools import lru_cache
from app.core.config import settings
from app.services.geocoding.nominatim import NominatimProvider
from app.services.places.overpass import OverpassProvider

@lru_cache(maxsize=1)
def geocoder() -> NominatimProvider:
    return NominatimProvider(
        endpoint=settings.nominatim_url,
        user_agent=settings.geo_user_agent,
        timeout=settings.geo_timeout_seconds,
        min_interval=settings.nominatim_min_interval_seconds,
    )

@lru_cache(maxsize=1)
def places_provider() -> OverpassProvider:
    return OverpassProvider(
        endpoint=settings.overpass_url,
        timeout=settings.overpass_timeout_seconds,
        user_agent=settings.geo_user_agent,
    )
