"""Provider contract for worldwide geocoding."""
from __future__ import annotations
from typing import Protocol

class GeocodingProvider(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        """Return normalized location candidates."""
