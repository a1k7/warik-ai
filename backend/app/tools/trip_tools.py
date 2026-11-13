"""AI Trip Planner — Phase 6: detailed, Ollama-assisted itineraries."""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from datetime import datetime, timedelta
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from app.agents.llm_provider import get_provider
from app.core.config import settings
from app.services.geospatial import geocoder, places_provider
from app.models import SavedTrip
from app.schemas.trip import (
    BudgetItem, ItineraryActivity, ItineraryDay, MealSuggestion,
    StructuredItinerary, TripBudget, HotelItem
)
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.tools.place_utils import (
    deduplicate_places, haversine_km, normalize_name,
    osm_map_url, google_maps_directions_url,
)
from app.tools.travel_apis import StayApiHotelTool, HotelInput

GEOAPIFY_GEOCODE = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES = "https://api.geoapify.com/v2/places"

ATTRACTION_CATEGORIES = "tourism.sights,tourism.attraction,entertainment.museum,building.historic,heritage,leisure.park,natural"
RESTAURANT_CATEGORIES = "catering.restaurant,catering.cafe"

DEFAULT_RADIUS_M = 35000
RESTAURANT_RADIUS_M = 15000

BASE_ACCOM_PER_NIGHT = 1500
BASE_FOOD_PER_DAY_PER_PERSON = 700
BASE_LOCAL_PER_DAY = 400
BASE_MISC_PER_DAY = 250

COST_INDEX = {
    "kochi": 1.1, "cochin": 1.1, "munnar": 1.0, "alleppey": 1.0, "alappuzha": 1.0,
    "mumbai": 1.6, "delhi": 1.5, "new delhi": 1.5, "bangalore": 1.4, "bengaluru": 1.4,
    "jaipur": 0.9, "udaipur": 0.9, "jodhpur": 0.9, "kolkata": 0.9, "darjeeling": 0.8,
    "goa": 1.4, "panaji": 1.4, "varanasi": 0.7, "agra": 0.8, "amritsar": 0.8,
    "kerala": 1.1, "karnataka": 1.3, "tamil nadu": 1.1, "maharashtra": 1.5,
}

# Fallback coordinates — prevents geocoding failures from wiping out a city
KNOWN_CITIES = {
    "kochi": {"name": "Kochi", "state": "Kerala", "country": "India", "lat": 9.9312, "lon": 76.2673},
    "cochin": {"name": "Kochi", "state": "Kerala", "country": "India", "lat": 9.9312, "lon": 76.2673},
    "munnar": {"name": "Munnar", "state": "Kerala", "country": "India", "lat": 10.0889, "lon": 77.0595},
    "alleppey": {"name": "Alappuzha", "state": "Kerala", "country": "India", "lat": 9.4981, "lon": 76.3388},
    "alappuzha": {"name": "Alappuzha", "state": "Kerala", "country": "India", "lat": 9.4981, "lon": 76.3388},
    "trivandrum": {"name": "Thiruvananthapuram", "state": "Kerala", "country": "India", "lat": 8.5241, "lon": 76.9366},
    "thekkady": {"name": "Thekkady", "state": "Kerala", "country": "India", "lat": 9.5850, "lon": 77.1588},
    "bangalore": {"name": "Bengaluru", "state": "Karnataka", "country": "India", "lat": 12.9716, "lon": 77.5946},
    "bengaluru": {"name": "Bengaluru", "state": "Karnataka", "country": "India", "lat": 12.9716, "lon": 77.5946},
    "mumbai": {"name": "Mumbai", "state": "Maharashtra", "country": "India", "lat": 19.0760, "lon": 72.8777},
    "delhi": {"name": "New Delhi", "state": "Delhi", "country": "India", "lat": 28.6139, "lon": 77.2090},
    "new delhi": {"name": "New Delhi", "state": "Delhi", "country": "India", "lat": 28.6139, "lon": 77.2090},
    "jaipur": {"name": "Jaipur", "state": "Rajasthan", "country": "India", "lat": 26.9124, "lon": 75.7873},
    "agra": {"name": "Agra", "state": "Uttar Pradesh", "country": "India", "lat": 27.1767, "lon": 78.0081},
    "udaipur": {"name": "Udaipur", "state": "Rajasthan", "country": "India", "lat": 24.5854, "lon": 73.7125},
    "goa": {"name": "Panaji", "state": "Goa", "country": "India", "lat": 15.4909, "lon": 73.8278},
    "panaji": {"name": "Panaji", "state": "Goa", "country": "India", "lat": 15.4909, "lon": 73.8278},
    "kolkata": {"name": "Kolkata", "state": "West Bengal", "country": "India", "lat": 22.5726, "lon": 88.3639},
    "chennai": {"name": "Chennai", "state": "Tamil Nadu", "country": "India", "lat": 13.0827, "lon": 80.2707},
}

STATE_TO_CITIES = {
    "kerala": ["Kochi", "Munnar", "Alleppey"],
    "rajasthan": ["Jaipur", "Udaipur", "Jodhpur"],
    "punjab": ["Amritsar", "Chandigarh"],
    "west bengal": ["Kolkata", "Darjeeling"],
    "maharashtra": ["Mumbai", "Pune"],
    "tamil nadu": ["Chennai", "Madurai"],
    "karnataka": ["Bangalore", "Mysore"],
    "goa": ["Panaji", "Calangute"],
    "uttar pradesh": ["Agra", "Varanasi"],
    "delhi": ["New Delhi"],
}


def get_cost_index(city_name: str) -> float:
    return COST_INDEX.get(city_name.lower().strip(), 1.0)


class ItineraryInput(BaseModel):
    destination: str
    days: int = Field(ge=1, le=14)
    budget: Optional[float] = None
    travellers: int = Field(default=1, ge=1, le=20)
    origin: Optional[str] = None
    include_hotels: bool = False
    check_in: Optional[str] = None
    check_out: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# GEOCODING
# ═══════════════════════════════════════════════════════════

def _geocode_place(place_name: str) -> Optional[dict]:
    key = place_name.lower().strip()
    if key in KNOWN_CITIES:
        return {"type": "city", **KNOWN_CITIES[key]}

    if settings.geoapify_api_key:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    GEOAPIFY_GEOCODE,
                    params={
                        "text": place_name,
                        "limit": 1,
                        "apiKey": settings.geoapify_api_key,
                    },
                )
                res.raise_for_status()
                data = res.json()

            features = data.get("features", []) if isinstance(data, dict) else []
            if features:
                props = features[0].get("properties", {})
                lat = float(props["lat"])
                lon = float(props["lon"])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return {
                        "name": str(
                            props.get("city")
                            or props.get("county")
                            or place_name
                        ).strip(),
                        "state": str(props.get("state") or "").strip(),
                        "country": str(props.get("country") or "").strip(),
                        "lat": lat,
                        "lon": lon,
                        "type": "city",
                        "source": "Geoapify",
                    }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError):
            pass

    try:
        candidates = geocoder().search(place_name, limit=5)
    except Exception:
        return None

    accepted_types = {
        "city", "town", "village", "municipality", "administrative"
    }
    for candidate in candidates:
        if str(candidate.get("type") or "").lower() not in accepted_types:
            continue
        try:
            lat = float(candidate["lat"])
            lon = float(candidate["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        if not str(candidate.get("name") or "").strip():
            continue
        return {
            **candidate,
            "name": str(candidate["name"]).strip(),
            "lat": lat,
            "lon": lon,
            "source": candidate.get("source") or "OpenStreetMap Nominatim",
        }

    return None

def _geocode_destination(destination: str) -> tuple[list[dict], Optional[str]]:
    """Resolve one destination or an explicitly separated multi-stop route.

    Commas are not treated as route separators initially because they commonly
    delimit administrative context (city, state, country). We first try the
    complete place string, then fall back to comma-separated destinations only
    when the complete string cannot be resolved.
    """
    raw = str(destination or "").strip()
    if not raw:
        return [], "I couldn't verify a destination because none was provided."

    # Explicit route language is unambiguous and should be split first.
    route_parts = re.split(r"\s+and\s+|\s+to\s+|\s+covering\s+", raw, flags=re.IGNORECASE)
    has_route_separator = len(route_parts) > 1

    if not has_route_separator:
        # Preserve administrative commas: e.g. "Jaipur, Rajasthan, India".
        whole_place = _geocode_place(raw)
        if whole_place:
            return [whole_place], None

        # A comma list can still represent multiple destinations (e.g. Paris, Tokyo).
        # Only use this fallback after the complete query fails.
        candidates = [part.strip() for part in raw.split(",") if len(part.strip()) > 2]
    else:
        candidates = [part.strip() for part in route_parts if len(part.strip()) > 2]

    cities = []
    seen = set()

    for part in candidates:
        key = part.lower().strip()
        if key in STATE_TO_CITIES:
            for city_name in STATE_TO_CITIES[key]:
                if city_name.lower() not in seen:
                    city = _geocode_place(city_name)
                    if city:
                        cities.append(city)
                        seen.add(city_name.lower())
            continue

        city = _geocode_place(part)
        if city and city.get("name", "").lower() not in seen:
            cities.append(city)
            seen.add(city.get("name", "").lower())

    if not cities:
        return [], f"I couldn't verify the destination '{raw}'. Please provide a city or a more specific location."
    return cities, None


# ═══════════════════════════════════════════════════════════
# PLACE FETCHING
# ═══════════════════════════════════════════════════════════

def _fetch_places(city: dict, categories: str, limit: int, radius_m: int) -> list[dict]:
    if settings.geoapify_api_key:
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(
                    GEOAPIFY_PLACES,
                    params={
                        "categories": categories,
                        "filter": f"circle:{city['lon']},{city['lat']},{radius_m}",
                        "limit": limit,
                        "apiKey": settings.geoapify_api_key,
                    },
                )
                res.raise_for_status()
                data = res.json()

            places = []
            features = data.get("features", []) if isinstance(data, dict) else []
            for feature in features:
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [])
                if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                    continue
                try:
                    lon, lat = float(coords[0]), float(coords[1])
                except (TypeError, ValueError):
                    continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue

                raw_tags = (
                    (props.get("datasource", {}) or {}).get("raw", {}) or {}
                )
                fee = raw_tags.get("fee") or raw_tags.get("charge")
                entry_fee = (
                    "Free"
                    if fee is not None and str(fee).lower() in ("no", "false", "0")
                    else (str(fee) if fee is not None else None)
                )
                name = str(props.get("name") or "").strip()
                if len(name) < 3:
                    continue

                places.append({
                    "name": name,
                    "address": str(
                        props.get("address_line2") or props.get("formatted") or ""
                    ).strip(),
                    "city": city["name"],
                    "lat": lat,
                    "lon": lon,
                    "category": (props.get("categories") or [None])[0],
                    "opening_hours": str(
                        props.get("opening_hours") or ""
                    ).strip() or None,
                    "entry_fee": entry_fee,
                    "image_url": raw_tags.get("image") or raw_tags.get("image_url"),
                    "wikimedia_commons": raw_tags.get("wikimedia_commons"),
                    "wikipedia": raw_tags.get("wikipedia"),
                    "wikidata": raw_tags.get("wikidata"),
                    "source": "Geoapify",
                })

            if places:
                return places[:limit]
        except (
            httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError
        ):
            pass

    kind = (
        "restaurant"
        if "catering" in categories or "restaurant" in categories
        else "attraction"
    )
    try:
        places = places_provider().search(
            city,
            kind=kind,
            limit=limit,
            radius_m=radius_m,
        )
        for place in places:
            place.setdefault("source", "OpenStreetMap")
        return places[:limit]
    except Exception:
        return []

def _is_valid_place(place: dict) -> bool:
    """Lenient validation — only reject obvious commercial noise."""
    name = normalize_name(place.get("name", ""))
    if len(name) < 3:
        return False
    # Reject obvious junk
    junk_words = ["printer", "store", "shop", "office", "bank", "atm", "parking", "bus stop", "petrol", "fuel", "pharmacy", "hospital", "clinic"]
    if any(w in name for w in junk_words):
        return False
    return True


# ═══════════════════════════════════════════════════════════
# DESCRIPTION GENERATOR — NEVER DROPS A PLACE
# ═══════════════════════════════════════════════════════════

def _generate_descriptions(names: list[str], city_name: str) -> dict[str, str]:
    """Return conservative descriptions without inventing place facts."""
    return {
        name: (
            f"A place listed in {city_name}. Confirm visitor access, current hours, "
            "and any entry requirements before visiting."
        )
        for name in names
    }

@lru_cache(maxsize=512)
def _fetch_commons_image(place_name: str, city_name: str) -> dict:
    """Find a relevant Wikimedia Commons image with attribution."""
    query = f'"{place_name}" "{city_name}" India'

    try:
        response = httpx.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f'filetype:bitmap {query}',
                "gsrnamespace": 6,
                "gsrlimit": 5,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 1200,
                "format": "json",
            },
            headers={
                "User-Agent": "WarikAI/1.0 (travel image attribution)"
            },
            timeout=8.0,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})

        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if not info_list:
                continue

            info = info_list[0]
            metadata = info.get("extmetadata", {})

            image_url = info.get("thumburl") or info.get("url")
            source_url = info.get("descriptionurl")

            if not image_url or not source_url:
                continue

            artist = metadata.get("Artist", {}).get("value", "")
            license_name = metadata.get("LicenseShortName", {}).get("value", "")

            return {
                "image_url": image_url,
                "image_credit": (
                    f"{artist} · {license_name}"
                    if artist and license_name
                    else artist or license_name or "Wikimedia Commons"
                ),
                "image_source_url": source_url,
            }

    except Exception:
        pass

    return {}

def _build_activity(place: dict, slot: str, time_str: str, description: str) -> ItineraryActivity:
    image = {}

    existing_image = place.get("image_url")
    if isinstance(existing_image, str) and existing_image.startswith("https://"):
        image = {
            "image_url": existing_image,
            "image_credit": "Geoapify/OSM source metadata",
            "image_source_url": existing_image,
        }
    else:
        image = _fetch_commons_image(
            place["name"],
            place.get("city", ""),
        )

    return ItineraryActivity(
        name=place["name"],
        description=description,
        slot=slot,
        suggested_time=time_str,
        duration_min=90,
        opening_hours=place.get("opening_hours"),
        entry_fee=place.get("entry_fee"),
        lat=place["lat"],
        lon=place["lon"],
        source=place.get("source") or "Unknown source",
        map_url=osm_map_url(place["lat"], place["lon"]),
        category=place.get("category"),
        image_url=image.get("image_url"),
        image_credit=image.get("image_credit"),
        image_source_url=image.get("image_source_url"),
        verification={
            "source_record_found": True,
            "coordinates_available": True,
            "category_tag_present": bool(place.get("category")),
            "tourism_suitability_verified": False,
            "hours_verified": False,
            "price_verified": False,
        },
    )


def _schedule_places(places: list[dict], descriptions: dict[str, str]) -> tuple[list, list, list]:
    """Group places into broad day periods without inventing visit times."""
    morning, afternoon, evening = [], [], []
    slots = ("morning", "afternoon", "evening")
    groups = {"morning": morning, "afternoon": afternoon, "evening": evening}

    for i, place in enumerate(places[:6]):
        slot = slots[i % len(slots)]
        activity = _build_activity(
            place,
            slot,
            None,
            descriptions.get(
                place["name"],
                f"Place listed in {place.get('city', 'the destination')}.",
            ),
        )
        groups[slot].append(activity)

    return morning, afternoon, evening


def _allocate_days(cities: list[dict], days: int) -> list[dict]:
    """Distribute days evenly across cities."""
    n = len(cities)
    per = {c["name"]: days // n for c in cities}
    for i in range(days - sum(per.values())):
        per[cities[i % n]["name"]] += 1
    return per


def _allocate_hotel_dates(
    cities: list[dict],
    per_city: dict[str, int],
    check_in: str,
) -> list[dict]:
    """
    Allocate consecutive hotel stays using the itinerary's city order.

    Each allocated itinerary day represents one overnight stay.
    The traveller checks out on the morning after the final allocated day.
    """
    current_date = datetime.strptime(check_in, "%Y-%m-%d").date()
    stays = []

    for city in cities:
        city_name = city["name"]
        nights = per_city.get(city_name, 0)

        if nights <= 0:
            continue

        checkout = current_date + timedelta(days=nights)

        stays.append({
            "city": city_name,
            "check_in": current_date.isoformat(),
            "check_out": checkout.isoformat(),
            "nights": nights,
        })

        current_date = checkout

    return stays

# ═══════════════════════════════════════════════════════════
# MAIN TOOL
# ═══════════════════════════════════════════════════════════

class GenerateAdvancedItineraryTool(BaseTool):
    name = "generate_advanced_itinerary"
    description = "Generate a detailed, verified day-by-day itinerary with real places, restaurants, and hotels."
    input_schema = ItineraryInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ItineraryInput) -> ToolResult:
        try:
            cities, err = _geocode_destination(params.destination)
            if err:
                return ToolResult(success=False, message=err)

            # Fetch places + restaurants per city
            places_by_city = {}
            restaurants_by_city = {}
            for city in cities:
                raw = _fetch_places(city, ATTRACTION_CATEGORIES, 20, DEFAULT_RADIUS_M)
                valid = [p for p in raw if _is_valid_place(p)]
                places_by_city[city["name"]] = deduplicate_places(valid)

                raw_rest = _fetch_places(city, RESTAURANT_CATEGORIES, 10, RESTAURANT_RADIUS_M)
                valid_rest = [p for p in raw_rest if _is_valid_place(p)]
                restaurants_by_city[city["name"]] = deduplicate_places(valid_rest)

            # Get descriptions for all places (Ollama, with fallback)
            all_names = []
            for places in places_by_city.values():
                all_names.extend(p["name"] for p in places)
            descriptions = _generate_descriptions(all_names, cities[0]["name"])

            # Allocate days
            per_city = _allocate_days(cities, params.days)

            # Build itinerary
            itinerary_days = []
            global_used = set()
            day_num = 1
            prev_city = None

            for city in cities:
                city_name = city["name"]
                places = places_by_city[city_name]
                rests = restaurants_by_city.get(city_name, [])
                city_days = per_city[city_name]

                for local_day in range(city_days):
                    is_transfer = (prev_city is not None and prev_city != city_name and local_day == 0)

                    # Pick next batch of 2-3 places for this day
                    available = [p for p in places if p["name"] not in global_used]
                    batch = available[:3]

                    if batch:
                        for p in batch:
                            global_used.add(p["name"])

                    morning, afternoon, evening = _schedule_places(batch, descriptions)

                    # Meals from restaurants in this city
                    meals = []
                    if rests:
                        r = rests[local_day % len(rests)]
                        meals.append(MealSuggestion(
                            name=r["name"],
                            category=r.get("category"),
                            address=r.get("address"),
                            map_url=osm_map_url(r["lat"], r["lon"]),
                            source=r.get("source") or "Unknown source",
                        ))

                    # Transfer notes
                    trans_notes = []
                    if is_transfer:
                        prev_city_obj = next((c for c in cities if c["name"] == prev_city), None)
                        if prev_city_obj:
                            trans_notes.append(
                                f"Intercity transfer: {prev_city} → {city_name}. "
                                "Check a current route planner for road distance, journey time, "
                                "and available transport before departure."
                            )

                    # Day title
                    if is_transfer:
                        day_title = f"Day {day_num} — Travel to {city_name}"
                    elif local_day == 0:
                        day_title = f"Day {day_num} — Arrival in {city_name}"
                    else:
                        day_title = f"Day {day_num} — Exploring {city_name}"

                    itinerary_days.append(ItineraryDay(
                        day=day_num,
                        title=day_title,
                        city=city_name,
                        morning=morning,
                        afternoon=afternoon,
                        evening=evening,
                        meal_suggestions=meals,
                        transport_notes=trans_notes,
                    ))
                    day_num += 1

                prev_city = city_name

            # Date-aware hotel searches for each itinerary city.
            hotels = []
            hotel_search_failures = []

            if params.include_hotels and params.check_in and params.check_out:
                try:
                    # Validate both dates before making any provider calls.
                    datetime.strptime(params.check_out, "%Y-%m-%d")
                    hotel_tool = StayApiHotelTool()
                    hotel_stays = _allocate_hotel_dates(
                        cities=cities,
                        per_city=per_city,
                        check_in=params.check_in,
                    )

                    expected_checkout = (
                        hotel_stays[-1]["check_out"] if hotel_stays else None
                    )

                    if expected_checkout != params.check_out:
                        hotel_search_failures.append(
                            "Hotel allocation checkout date does not match "
                            "the requested trip checkout date. "
                            f"Expected {expected_checkout}; received {params.check_out}."
                        )
                    else:
                        for stay in hotel_stays:
                            try:
                                res = hotel_tool.execute(
                                    ctx,
                                    HotelInput(
                                        city=stay["city"],
                                        check_in=stay["check_in"],
                                        check_out=stay["check_out"],
                                        travellers=params.travellers,
                                        # The full trip budget must not be applied
                                        # independently to each city's stay.
                                        budget=None,
                                    ),
                                )

                                if not res.success:
                                    hotel_search_failures.append(
                                        f"{stay['city']}: {res.message}"
                                    )
                                    continue

                                result_data = res.data or {}
                                if not isinstance(result_data, dict):
                                    hotel_search_failures.append(
                                        f"{stay['city']}: hotel provider returned invalid data."
                                    )
                                    continue

                                hotel_items = result_data.get("items", []) or []
                                if not hotel_items:
                                    hotel_search_failures.append(
                                        f"{stay['city']}: {res.message or 'No hotels found.'}"
                                    )
                                    continue

                                for hotel in hotel_items[:2]:
                                    if not isinstance(hotel, dict):
                                        continue

                                    hotels.append(
                                        HotelItem(
                                            name=(
                                                f"{hotel.get('name', 'Unnamed hotel')} "
                                                f"({stay['city']})"
                                            ),
                                            address=hotel.get("address", ""),
                                            price=hotel.get("total_stay", "Not available"),
                                            rating="Not provided",
                                            booking_url=hotel.get("booking_url", ""),
                                            image_url=hotel.get("image_url", ""),
                                            city=stay["city"],
                                            check_in=stay["check_in"],
                                            check_out=stay["check_out"],
                                            price_per_night=hotel.get("price_per_night"),
                                        )
                                    )

                            except Exception as exc:
                                hotel_search_failures.append(
                                    f"{stay['city']}: {str(exc)}"
                                )

                except Exception as exc:
                    # Hotel lookup is supplementary: retain the itinerary if
                    # date parsing or hotel allocation fails.
                    hotel_search_failures.append(
                        f"Hotel allocation failed: {str(exc)}"
                    )

            # Budget
            budget = self._compute_budget(params, cities)

            dest_display = " → ".join(c["name"] for c in cities)
            itinerary = StructuredItinerary(
                destination=dest_display,
                travellers=params.travellers,
                days=itinerary_days,
                budget=budget,
                notes=[
                    "Place listings are sourced from Geoapify/OpenStreetMap; listings do not confirm visitor access or current operating status.",
                    "Intercity road distances and journey times are not verified by this itinerary.",
                    "Descriptions are conservative prompts to verify visitor details, not independently researched facts.",
                    *[
                        f"Hotel search issue: {failure}"
                        for failure in hotel_search_failures
                    ],
                ],
                hotels=hotels,
            )
            return ToolResult(
                success=True,
                message=f"Your {params.days}-day itinerary for {dest_display} is ready.",
                data=itinerary.model_dump(mode="json"),
            )

        except Exception as exc:
            import traceback
            traceback.print_exc()
            return ToolResult(success=False, message=f"Trip planning error: {exc}")

    def _compute_budget(self, params: ItineraryInput, cities: list[dict]) -> TripBudget:
        travellers = max(1, params.travellers)
        nights = max(0, params.days - 1)
        rooms = math.ceil(travellers / 2)
        idx = get_cost_index(cities[0]["name"])

        items = []
        excludes = []

        if len(cities) > 1:
            total_km = sum(
                haversine_km(cities[i]["lat"], cities[i]["lon"], cities[i+1]["lat"], cities[i+1]["lon"])
                for i in range(len(cities) - 1)
            )
            intercity = round(total_km * 1.5 * travellers)
            items.append(BudgetItem(
                category="Intercity transport",
                amount=intercity,
                classification="ESTIMATE",
                note=f"~{total_km:.0f} km total",
            ))
        else:
            items.append(BudgetItem(
                category="Intercity transport",
                amount=None,
                classification="UNAVAILABLE",
                note="Add origin city to enable.",
            ))
            excludes.append("Intercity transport")

        acc = round(BASE_ACCOM_PER_NIGHT * idx * nights * rooms)
        food = round(BASE_FOOD_PER_DAY_PER_PERSON * idx * params.days * travellers)
        local = round(BASE_LOCAL_PER_DAY * idx * params.days)
        misc = round(BASE_MISC_PER_DAY * idx * params.days)

        if nights > 0:
            items.append(BudgetItem(
                category="Accommodation",
                amount=acc,
                classification="ESTIMATE",
                note=f"{nights} nights, {rooms} rooms",
            ))
        else:
            items.append(BudgetItem(category="Accommodation", amount=0, classification="UNAVAILABLE", note="Day trip."))
            excludes.append("Accommodation")

        items.append(BudgetItem(category="Food", amount=food, classification="ESTIMATE"))
        items.append(BudgetItem(category="Local transport", amount=local, classification="ESTIMATE"))
        items.append(BudgetItem(
            category="Attraction entry fees",
            amount=None,
            classification="UNAVAILABLE",
            note="Verify at venue.",
        ))
        excludes.append("Attraction entry fees")
        items.append(BudgetItem(category="Miscellaneous", amount=misc, classification="ESTIMATE"))

        total = sum(i.amount for i in items if i.amount is not None)
        remaining = (params.budget - total) if params.budget else None

        return TripBudget(
            items=items,
            user_budget=params.budget,
            travellers=travellers,
            total_estimate=round(total, 2) if total > 0 else None,
            remaining=round(remaining, 2) if remaining is not None else None,
            per_person=round(total / travellers, 2) if total else None,
            excludes=excludes,
            is_partial=bool(excludes),
        )


class SaveTripInput(BaseModel):
    destination: str
    days: int
    itinerary_json: str


class SaveTripTool(BaseTool):
    name = "save_trip"
    description = "Save the generated itinerary to the user's saved trips."
    input_schema = SaveTripInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: SaveTripInput) -> ToolResult:
        try:
            itinerary_data = json.loads(params.itinerary_json)
        except json.JSONDecodeError:
            return ToolResult(success=False, message="Invalid itinerary data.")
        trip = SavedTrip(
            user_id=ctx.user.id,
            destination=params.destination,
            days=params.days,
            itinerary_data=itinerary_data,
        )
        ctx.db.add(trip)
        ctx.db.commit()
        ctx.db.refresh(trip)
        return ToolResult(
            success=True,
            message=f"Saved your trip to {params.destination}!",
            data={"saved_trip_id": trip.id},
        )

    def verify(self, ctx: ToolContext, params: SaveTripInput, result: ToolResult) -> dict:
        saved_trip_id = (result.data or {}).get("saved_trip_id")
        saved = (ctx.db.query(SavedTrip).filter(
            SavedTrip.id == saved_trip_id, SavedTrip.user_id == ctx.user.id
        ).one_or_none() if saved_trip_id else None)
        try:
            expected_itinerary = json.loads(params.itinerary_json)
        except (TypeError, json.JSONDecodeError):
            expected_itinerary = None
        matches = bool(saved and expected_itinerary is not None
                       and saved.destination == params.destination
                       and saved.days == params.days
                       and saved.itinerary_data == expected_itinerary)
        return {"verified": matches, "method": "database_record_lookup",
                "evidence": {"saved_trip_id": saved_trip_id, "record_found": saved is not None,
                             "user_scope_checked": True, "itinerary_matched": matches}}
