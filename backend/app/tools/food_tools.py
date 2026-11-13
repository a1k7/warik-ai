"""Food discovery tools — strict location, no defaults, no hallucination."""
import httpx
import re
import math
from urllib.parse import quote
from typing import Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.core.config import settings
from app.services.geospatial import geocoder, places_provider

# ─── Canonical city → coordinates ───────────────────────────
# If the input matches one of these exactly (case-insensitive),
# we SKIP Geoapify and use these coords. No ambiguity possible.
KNOWN_CITIES = {
    "delhi": {"name": "Delhi", "lat": 28.6139, "lon": 77.2090, "country": "India"},
    "new delhi": {"name": "New Delhi", "lat": 28.6139, "lon": 77.2090, "country": "India"},
    "mumbai": {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777, "country": "India"},
    "bombay": {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777, "country": "India"},
    "bangalore": {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946, "country": "India"},
    "bengaluru": {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946, "country": "India"},
    "chennai": {"name": "Chennai", "lat": 13.0827, "lon": 80.2707, "country": "India"},
    "kolkata": {"name": "Kolkata", "lat": 22.5726, "lon": 88.3639, "country": "India"},
    "hyderabad": {"name": "Hyderabad", "lat": 17.3850, "lon": 78.4867, "country": "India"},
    "pune": {"name": "Pune", "lat": 18.5204, "lon": 73.8567, "country": "India"},
    "jaipur": {"name": "Jaipur", "lat": 26.9124, "lon": 75.7873, "country": "India"},
    "goa": {"name": "Panaji", "lat": 15.4909, "lon": 73.8278, "country": "India"},
    "panaji": {"name": "Panaji", "lat": 15.4909, "lon": 73.8278, "country": "India"},
    "kochi": {"name": "Kochi", "lat": 9.9312, "lon": 76.2673, "country": "India"},
    "cochin": {"name": "Kochi", "lat": 9.9312, "lon": 76.2673, "country": "India"},
}


def _geocode_location(location: str) -> Optional[dict]:
    """Resolve a city using known coordinates, Geoapify, then Nominatim."""
    key = location.lower().strip()
    if key in KNOWN_CITIES:
        return KNOWN_CITIES[key]

    if settings.geoapify_api_key:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    "https://api.geoapify.com/v1/geocode/search",
                    params={
                        "text": location,
                        "limit": 1,
                        "apiKey": settings.geoapify_api_key,
                    },
                )
                res.raise_for_status()
                data = res.json()

            features = data.get("features") or []
            if features:
                props = features[0].get("properties") or {}
                lat, lon = props.get("lat"), props.get("lon")
                returned = (props.get("city") or "").strip()
                if lat is not None and lon is not None:
                    if not returned or (
                        key in returned.lower() or returned.lower() in key
                    ):
                        return {
                            "name": returned or location.title(),
                            "lat": float(lat),
                            "lon": float(lon),
                            "country": props.get("country"),
                        }
        except Exception:
            pass

    try:
        results = geocoder().search(location, limit=5)
    except Exception:
        return None

    allowed_types = {
        "city", "town", "village", "municipality", "administrative"
    }
    for result in results or []:
        if not isinstance(result, dict):
            continue
        place_type = str(
            result.get("type") or result.get("addresstype") or ""
        ).lower()
        if place_type not in allowed_types:
            continue
        try:
            lat = float(result["lat"])
            lon = float(result["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        return {
            "name": result.get("name") or location.title(),
            "lat": lat,
            "lon": lon,
            "country": result.get("country"),
        }
    return None


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return R * 2 * math.asin(math.sqrt(a))


class DiscoverFoodInput(BaseModel):
    location: str = Field(..., min_length=2)
    query: str = Field(default="restaurant")
    category: str = Field(default="restaurant")
    budget: Optional[float] = Field(default=None)


class DiscoverFoodTool(BaseTool):
    name = "discover_food"
    description = "Find real restaurants in a specific city. No defaults — rejects ambiguous locations."
    capability = "food"
    input_schema = DiscoverFoodInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: DiscoverFoodInput) -> ToolResult:
        location_raw = (params.location or "").strip()

        # ─── STRICT INPUT VALIDATION ───
        if not location_raw:
            return ToolResult(success=False, message="I need a city name to search.")
        if len(location_raw) > 40:
            return ToolResult(success=False,
                              message=f"'{location_raw[:30]}...' is too long to be a city name. Which city?")
        if len(location_raw.split()) > 4:
            return ToolResult(success=False,
                              message=f"'{location_raw}' doesn't look like a city. Which city?")

        coords = _geocode_location(location_raw)
        if not coords:
            return ToolResult(success=False,
                              message=f"I couldn't find '{location_raw}' as a city. Could you use a major nearby city?")

        city_name = coords["name"]
        city_lat = coords["lat"]
        city_lon = coords["lon"]

        try:
            places = places_provider().search(
                {
                    "name": city_name,
                    "lat": city_lat,
                    "lon": city_lon,
                },
                kind="restaurant",
                limit=30,
                radius_m=15000,
            )
        except Exception:
            return ToolResult(
                success=False,
                message=(
                    f"Restaurant discovery is temporarily unavailable in "
                    f"{city_name}. Please try again shortly."
                ),
                data={
                    "provider_status": "unavailable",
                    "location": city_name,
                },
            )

        valid_places = []
        seen_names = set()

        for place in places:
            name = str(place.get("name") or "").strip()
            if len(name) < 3 or name.lower() in seen_names:
                continue

            try:
                plat = float(place["lat"])
                plon = float(place["lon"])
            except (KeyError, TypeError, ValueError):
                continue

            dist_km = _haversine_km(city_lat, city_lon, plat, plon)
            if dist_km > 15:
                continue

            seen_names.add(name.lower())
            valid_places.append({
                "name": name,
                "address": place.get("address") or city_name,
                "lat": plat,
                "lon": plon,
                "distance_km": round(dist_km, 1),
                "maps_url": (
                    f"https://www.openstreetmap.org/?mlat={plat}&mlon={plon}"
                    f"#map=16/{plat}/{plon}"
                ),
                "zomato_url": f"https://www.zomato.com/search?q={quote(name)}",
                "swiggy_url": f"https://www.swiggy.com/search?query={quote(name)}",
                "category": place.get("category") or "restaurant",
                "opening_hours": place.get("opening_hours"),
                "dietary_tags": place.get("dietary_tags") or {},
                "source": place.get("source") or "OpenStreetMap",
            })

        valid_places.sort(key=lambda place: place["distance_km"])

        if not valid_places:
            return ToolResult(
                success=True,
                message=(
                    f"No OpenStreetMap restaurant listings were found in {city_name}. "
                    "This does not establish that no restaurants are available."
                ),
                data={
                    "type": "food_list",
                    "items": [],
                    "search_context": {
                        "location": city_name,
                        "query": params.query,
                        "budget": params.budget,
                        "source": "OpenStreetMap",
                        "menu_prices_verified": False,
                        "dietary_suitability_verified": False,
                    },
                },
            )

        valid_places.sort(key=lambda p: p["distance_km"])

        return ToolResult(
            success=True,
            message=f"Found {len(valid_places)} OpenStreetMap-listed places in {city_name}.",
            data={
                "type": "food_list",
                "items": valid_places[:5],
                "search_context": {
                    "location": city_name,
                    "query": params.query,
                    "budget": params.budget,
                    "source": "OpenStreetMap",
                    "menu_prices_verified": False,
                    "dietary_suitability_verified": False,
                },
            },
        )


class SaveFavoriteRestaurantInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)


class SaveFavoriteRestaurantTool(BaseTool):
    name = "save_favorite_restaurant"
    description = "Save a restaurant to favorites."
    input_schema = SaveFavoriteRestaurantInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: SaveFavoriteRestaurantInput) -> ToolResult:
        try:
            from app.models import FavoriteRestaurant
            fav = FavoriteRestaurant(user_id=ctx.user.id, name=params.name,
                                     location=params.location, notes=params.notes)
            ctx.db.add(fav)
            ctx.db.commit()
            return ToolResult(success=True, message=f"Saved {params.name} to your favorites.")
        except Exception as e:
            ctx.db.rollback()
            return ToolResult(success=False, message=f"Could not save favorite: {e}")