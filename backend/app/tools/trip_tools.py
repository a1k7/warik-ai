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
    """Resolve a destination dynamically using configured geocoding providers."""
    query = " ".join(str(place_name or "").split())
    if not query:
        return None

    # Geoapify is optional. Nominatim is the independent fallback.
    if settings.geoapify_api_key:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    GEOAPIFY_GEOCODE,
                    params={
                        "text": query,
                        "limit": 1,
                        "apiKey": settings.geoapify_api_key,
                    },
                )
                response.raise_for_status()
                data = response.json()

            features = data.get("features", []) if isinstance(data, dict) else []
            if features:
                props = features[0].get("properties", {})
                lat = float(props["lat"])
                lon = float(props["lon"])

                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return {
                        "name": str(
                            props.get("city")
                            or props.get("town")
                            or props.get("county")
                            or props.get("name")
                            or query
                        ).strip(),
                        "state": str(props.get("state") or "").strip(),
                        "country": str(props.get("country") or "").strip(),
                        "lat": lat,
                        "lon": lon,
                        "type": "city",
                        "source": "Geoapify",
                    }
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ):
            pass

    try:
        candidates = geocoder().search(query, limit=5)
    except Exception:
        return None

    accepted_types = {
        "city",
        "town",
        "village",
        "municipality",
        "administrative",
    }

    for candidate in candidates:
        if str(candidate.get("type") or "").lower() not in accepted_types:
            continue

        try:
            lat = float(candidate["lat"])
            lon = float(candidate["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        name = str(candidate.get("name") or "").strip()

        if not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        return {
            **candidate,
            "name": name,
            "lat": lat,
            "lon": lon,
            "source": candidate.get("source") or "OpenStreetMap Nominatim",
        }

    return None


def _geocode_destination(destination: str) -> tuple[list[dict], Optional[str]]:
    """Resolve destinations dynamically without hardcoded location mappings."""
    raw = str(destination or "").strip()

    if not raw:
        return [], "I couldn't verify a destination because none was provided."

    route_parts = re.split(
        r"\s+and\s+|\s+to\s+|\s+covering\s+",
        raw,
        flags=re.IGNORECASE,
    )

    is_multi_stop = len(route_parts) > 1

    if not is_multi_stop:
        # Resolve the complete query first to preserve geographic context.
        whole_place = _geocode_place(raw)
        if whole_place:
            return [whole_place], None

        candidates = [
            part.strip()
            for part in raw.split(",")
            if len(part.strip()) > 2
        ]
    else:
        candidates = [
            part.strip()
            for part in route_parts
            if len(part.strip()) > 2
        ]

    cities = []
    seen = set()

    for part in candidates:
        city = _geocode_place(part)

        if not city:
            continue

        try:
            name = str(city.get("name") or part).strip()
            lat = float(city["lat"])
            lon = float(city["lon"])

            if not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            # Identity is based on the resolved place name AND coordinates.
            identity = (
                name.casefold(),
                round(lat, 5),
                round(lon, 5),
            )

        except (KeyError, TypeError, ValueError):
            continue

        if identity in seen:
            continue

        cities.append({
            **city,
            "name": name,
            "lat": lat,
            "lon": lon,
        })
        seen.add(identity)

    if not cities:
        return [], (
            f"I couldn't verify the destination '{raw}'. "
            "Please provide a city or a more specific location."
        )

    return cities, None

def _fetch_places(city: dict, categories: str, limit: int, radius_m: int) -> list[dict]:
    """Fetch real places, preferring Geoapify and falling back to Overpass."""
    if settings.geoapify_api_key:
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    GEOAPIFY_PLACES,
                    params={
                        "categories": categories,
                        "filter": f"circle:{city['lon']},{city['lat']},{radius_m}",
                        "limit": limit,
                        "apiKey": settings.geoapify_api_key,
                    },
                )
                response.raise_for_status()
                data = response.json()

            places = []
            features = data.get("features", []) if isinstance(data, dict) else []

            for feature in features:
                props = feature.get("properties", {})
                geometry = feature.get("geometry", {}) or {}
                coords = geometry.get("coordinates", [])

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

                place_categories = props.get("categories") or []

                places.append({
                    "name": name,
                    "address": str(
                        props.get("address_line2") or props.get("formatted") or ""
                    ).strip(),
                    "city": city["name"],
                    "lat": lat,
                    "lon": lon,
                    "category": place_categories[0] if place_categories else None,
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
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ):
            # Continue to the independent OpenStreetMap provider.
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
    except Exception as exc:
        raise RuntimeError(
            f"Place discovery failed for {city.get('name', 'destination')}: {exc}"
        ) from exc

    for place in places:
        place.setdefault("source", "OpenStreetMap")

    return places[:limit]

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
        """Return budget figures only when supported by price evidence."""
        travellers = max(1, params.travellers)
        nights = max(0, params.days - 1)
        rooms = math.ceil(travellers / 2)

        items = []
        excludes = []

        if len(cities) > 1:
            total_km = sum(
                haversine_km(
                    cities[i]["lat"],
                    cities[i]["lon"],
                    cities[i + 1]["lat"],
                    cities[i + 1]["lon"],
                )
                for i in range(len(cities) - 1)
            )
            transport_note = (
                f"Approximately {total_km:.0f} km straight-line distance; "
                "no verified transport fare available."
            )
        else:
            transport_note = (
                "No intercity route distance or verified transport fare available."
            )

        items.append(BudgetItem(
            category="Intercity transport",
            amount=None,
            classification="UNAVAILABLE",
            note=transport_note,
        ))
        excludes.append("Intercity transport")

        accommodation_note = (
            f"{nights} nights and {rooms} rooms; "
            "no verified accommodation quote available."
            if nights > 0
            else "No overnight stay planned; accommodation cost not applicable."
        )

        items.append(BudgetItem(
            category="Accommodation",
            amount=None,
            classification="UNAVAILABLE",
            note=accommodation_note,
        ))
        excludes.append("Accommodation")

        for category, note in (
            ("Food", "No sourced meal prices available."),
            ("Local transport", "No verified local transport fares available."),
            ("Attraction entry fees", "Verify fees directly with the venue."),
            ("Miscellaneous", "No sourced cost data available."),
        ):
            items.append(BudgetItem(
                category=category,
                amount=None,
                classification="UNAVAILABLE",
                note=note,
            ))
            excludes.append(category)

        return TripBudget(
            items=items,
            user_budget=params.budget,
            travellers=travellers,
            total_estimate=None,
            remaining=None,
            per_person=None,
            excludes=excludes,
            is_partial=True,
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
