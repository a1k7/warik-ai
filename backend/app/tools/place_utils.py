"""Place validation, deduplication and geo helpers for the trip planner."""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher

GENERIC_NAMES = {
    "rooftop view", "viewpoint", "view point", "scenic view", "city center", "city centre",
    "local market", "main market", "bus stand", "railway station", "airport", "mall",
    "shopping complex", "parking", "hotel", "restaurant", "cafe", "pink city", "old city",
    "new city", "old delhi", "new delhi"
}

EXCLUDED_CATEGORIES = {
    "place.neighbourhood", "place.city", "place.town", "place.village", "place.hamlet",
    "boundary.administrative", "office", "building.commercial", "building.industrial"
}

def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.lower().strip()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()

def is_valid_place_name(name: str) -> bool:
    if not name:
        return False
    stripped = name.strip()
    if len(stripped) < 3:
        return False
    if not re.search(r"[A-Za-z\u0900-\u097F]", stripped):
        return False
    if normalize_name(stripped) in GENERIC_NAMES:
        return False
    return True

def is_tourism_suitable(place: dict) -> bool:
    name = normalize_name(place.get("name", ""))

    # 1. Hard blacklist for commercial, government, and generic terms
    banned_words = [
        "printer", "press", "store", "shop", "office", "bank", "school", "college",
        "hospital", "clinic", "enterprise", "company", "hotel", "townhall", "town hall",
        "municipal", "corporation", "government", "police", "station", "post office",
        "rooftop", "viewpoint", "view point"
    ]
    if any(w in name for w in banned_words):
        return False

    # 2. Check OSM categories
    cat = str(place.get("category") or "").lower()
    if not cat:
        return False

    if any(ex in cat for ex in EXCLUDED_CATEGORIES):
        return False

    # 3. Must have a recognized tourism/historic/museum category
    allowed = [
        "tourism.sights", "tourism.attraction", "tourism.artwork",
        "entertainment.museum", "building.historic", "heritage",
        "religion.place_of_worship", "leisure.park", "leisure.garden",
        "natural.water", "natural.peak", "historic"
    ]
    if not any(a in cat for a in allowed):
        return False

    return True

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))

def osm_map_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"

def google_maps_directions_url(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"

def _completeness(p: dict) -> int:
    return sum(1 for k in ("name", "address", "lat", "lon", "category", "opening_hours") if p.get(k))

def deduplicate_places(
    places: list[dict],
    name_threshold: float = 0.85,
    coord_radius_m: float = 500.0,
) -> list[dict]:
    result: list[dict] = []
    for place in places:
        if place.get("lat") is None or place.get("lon") is None:
            continue
        duplicate = False
        for idx, existing in enumerate(result):
            na = normalize_name(place.get("name", ""))
            ne = normalize_name(existing.get("name", ""))

            if na == ne:
                duplicate = True
                break

            if (na in ne or ne in na) and len(min(na, ne, key=len)) > 5:
                duplicate = True
                break

            sim = name_similarity(place.get("name", ""), existing.get("name", ""))
            dist_km = haversine_km(float(place["lat"]), float(place["lon"]), float(existing["lat"]), float(existing["lon"]))

            if sim >= name_threshold or (dist_km * 1000.0 <= coord_radius_m and sim >= 0.4):
                if _completeness(place) > _completeness(existing):
                    result[idx] = place
                duplicate = True
                break
        if not duplicate:
            result.append(place)
    return result

def filter_by_name(places: list[dict], exclude_names: list[str], threshold: float = 0.85) -> list[dict]:
    excluded = [n for n in (exclude_names or []) if n]
    kept = []
    for p in places:
        if any(name_similarity(p.get("name", ""), ex) >= threshold for ex in excluded):
            continue
        kept.append(p)
    return kept
