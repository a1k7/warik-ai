"""Provider contract for nearby point-of-interest discovery."""
from __future__ import annotations
from typing import Protocol

class PlacesProvider(Protocol):
    def search(self, location: dict, *, kind: str, limit: int = 20, radius_m: int = 15000) -> list[dict]:
        """Return normalized nearby places."""
