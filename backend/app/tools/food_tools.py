"""Food discovery tools — strict location, no defaults, no hallucination."""
import math
from urllib.parse import quote
from typing import Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.services.geospatial import geocoder, places_provider

def _geocode_location(location: str) -> Optional[dict]:
    """Resolve a location dynamically through the configured geocoder."""
    try:
        results = geocoder().search(location, limit=5)
    except Exception:
        return None

    for result in results or []:
        if not isinstance(result, dict):
            continue

        try:
            lat = float(result["lat"])
            lon = float(result["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        name = str(result.get("name") or "").strip()
        if not name:
            continue

        return {
            "name": name,
            "lat": lat,
            "lon": lon,
            "country": result.get("country"),
            "state": result.get("state"),
            "display_name": result.get("display_name"),
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
    dietary_requirements: list[str] = Field(default_factory=list)
    party_size: Optional[int] = Field(default=None, ge=1)


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
        allowed_food_categories = {
            "restaurant",
            "cafe",
            "fast_food",
            "food_court",
        }

        for place in places:
            category = str(place.get("category") or "").strip().lower()
            if category not in allowed_food_categories:
                continue

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
                "zomato_url": (
                    f"https://www.zomato.com/search"
                    f"?q={quote(name + ' ' + city_name)}"
                ),
                "swiggy_url": (
                    f"https://www.swiggy.com/search"
                    f"?query={quote(name + ' ' + city_name)}"
                ),
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
                        "budget_fit_verified": False,
                        "dietary_suitability_verified": False,
                        "external_search_location_verified": False,
                        "dietary_requirements": params.dietary_requirements,
                        "party_size": params.party_size,
                    },
                },
            )

        valid_places.sort(key=lambda p: p["distance_km"])

        return ToolResult(
            success=True,
            message=(
                f"Found {len(valid_places)} OpenStreetMap-listed candidates in "
                f"{city_name}. Menu prices and dietary compatibility have not "
                "been verified, so I cannot confirm they meet your requirements "
                "or budget."
            ),
            data={
                "type": "food_list",
                "items": valid_places[:5],
                "search_context": {
                    "location": city_name,
                    "query": params.query,
                    "budget": params.budget,
                    "source": "OpenStreetMap",
                    "menu_prices_verified": False,
                    "budget_fit_verified": False,
                    "dietary_suitability_verified": False,
                    "external_search_location_verified": False,
                    "dietary_requirements": params.dietary_requirements,
                    "party_size": params.party_size,
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