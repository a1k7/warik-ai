
"""Warik AI travel tools — flights, hotels, places, cabs."""

import httpx
import json
import subprocess
import shutil
import re
import math

from urllib.parse import quote_plus, quote
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult
from app.core.config import settings
from app.services.geospatial import geocoder, places_provider



class AirportResolutionError(RuntimeError):
    """Raised when a provider prevents airport resolution."""


def get_iata(value: str) -> str:
    """Recognize the syntax of an explicitly supplied IATA code."""
    if not isinstance(value, str):
        return ""
    normalized = value.strip().upper()
    return normalized if re.fullmatch(r"[A-Z]{3}", normalized) else ""


def normalize_cli_city(city: str) -> str:
    """Preserve the user's original location text."""
    return city.strip() if isinstance(city, str) else ""


def resolve_airport_candidates(
    location: str,
    limit: int = 5,
) -> list[dict]:
    """Resolve arbitrary locations to nearby provider-recorded airports."""
    if not isinstance(location, str) or not location.strip():
        return []

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    try:
        provider = places_provider()

        # A three-letter input is only a possible IATA code.
        # Verify it against an actual airport record before accepting it.
        explicit_code = get_iata(location)
        if explicit_code:
            records = provider.search_airports_by_iata(
                explicit_code,
                limit=10,
            )
            return [
                {
                    **record,
                    "distance_km": 0.0,
                    "source": record.get("source", "OpenStreetMap"),
                }
                for record in records
                if str(record.get("iata") or "").upper() == explicit_code
            ][:limit]

        # Multiple geocoding results help with ambiguous place names.
        locations = geocoder().search(location.strip(), limit=5)

        if not locations:
            return []

        candidates_by_code = {}

        for resolved_location in locations:
            try:
                latitude = float(resolved_location["lat"])
                longitude = float(resolved_location["lon"])
            except (KeyError, TypeError, ValueError):
                continue

            airports = provider.search_airports(
                resolved_location,
                limit=100,
                radius_m=settings.airport_search_radius_m,
            )

            for airport in airports:
                code = str(airport.get("iata") or "").strip().upper()

                if not re.fullmatch(r"[A-Z]{3}", code):
                    continue

                try:
                    distance = haversine_km(
                        latitude,
                        longitude,
                        float(airport["lat"]),
                        float(airport["lon"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue

                candidate = {
                    **airport,
                    "iata": code,
                    "distance_km": round(distance, 2),
                    "matched_location": resolved_location.get(
                        "display_name",
                        resolved_location.get("name", location),
                    ),
                }

                existing = candidates_by_code.get(code)
                if (
                    existing is None
                    or candidate["distance_km"] < existing["distance_km"]
                ):
                    candidates_by_code[code] = candidate

        return sorted(
            candidates_by_code.values(),
            key=lambda item: item["distance_km"],
        )[:limit]

    except Exception as exc:
        raise AirportResolutionError(
            f"Airport provider resolution failed: {exc}"
        ) from exc


def format_price(amount: float, currency: str) -> str:
    curr = currency.upper().strip()

    if curr == "INR":
        return f"₹{amount:,.0f}"
    elif curr == "USD":
        return f"${amount:,.2f}"
    elif curr == "EUR":
        return f"€{amount:,.2f}"

    return f"{amount:,.2f} {curr}"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0

    lat1, lon1, lat2, lon2 = map(
        math.radians,
        [lat1, lon1, lat2, lon2],
    )

    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin((lon2 - lon1) / 2) ** 2
    )

    return R * 2 * math.asin(math.sqrt(a))


# ─── FLIGHTS ───────────────────────────────────────────────


class FlightInput(BaseModel):
    origin: str = Field(...)
    destination: str = Field(...)
    date: str = Field(...)


class RealFlightSearchTool(BaseTool):
    name = "search_flights_real"

    description = (
        "Search real-time flight options and return provider/Google Flights "
        "booking links. Does not reserve a seat, issue a ticket, "
        "or process payment."
    )

    input_schema = FlightInput
    requires_confirmation = False

    capability = "travel"

    provider_adapters = (
        {
            "provider_id": "trvl_cli",
            "display_name": "TRVL CLI adapter",
        },
    )

    supported_operations = ("search",)

    def execute(
        self,
        ctx: ToolContext,
        params: FlightInput,
    ) -> ToolResult:

        try:
            origin_airports = resolve_airport_candidates(params.origin)
            destination_airports = resolve_airport_candidates(
                params.destination
            )
        except AirportResolutionError as exc:
            search_query = (
                f"Flights from {params.origin.strip()} "
                f"to {params.destination.strip()} on {params.date}"
            )
            search_url = (
                "https://www.google.com/travel/flights?"
                f"q={quote_plus(search_query)}"
            )
            return ToolResult(
                success=True,
                message=(
                    "Airport data providers are temporarily unavailable. "
                    "No live inventory was queried. Use the search link "
                    "to check current routes and prices."
                ),
                data={
                    "type": "flight_list",
                    "items": [],
                    "search_url": search_url,
                    "live_inventory": False,
                    "resolution_status": "provider_unavailable",
                    "provider_error": str(exc),
                },
            )

        origin_iata = origin_airports[0]["iata"] if origin_airports else ""
        dest_iata = (
            destination_airports[0]["iata"]
            if destination_airports
            else ""
        )

        try:
            parsed_date = datetime.strptime(
                params.date,
                "%Y-%m-%d",
            )

            if parsed_date.strftime("%Y-%m-%d") != params.date:
                raise ValueError(
                    "Date must use YYYY-MM-DD format."
                )

        except (TypeError, ValueError):
            return ToolResult(
                success=False,
                message=(
                    "Flight search skipped: a valid date "
                    "in YYYY-MM-DD format is required."
                ),
            )

        if not origin_iata or not dest_iata:
            search_query = (
                f"Flights from {params.origin.strip()} "
                f"to {params.destination.strip()} on {params.date}"
            )
            search_url = (
                "https://www.google.com/travel/flights?"
                f"q={quote_plus(search_query)}"
            )
            return ToolResult(
                success=True,
                message=(
                    "Airport codes were not provided, so live flight "
                    "inventory was not queried. Use this search link "
                    "to check routes and current prices."
                ),
                data={
                    "type": "flight_list",
                    "items": [],
                    "search_url": search_url,
                    "live_inventory": False,
                    "resolution_status": "airport_not_found",
                    "origin_airport_candidates": origin_airports,
                    "destination_airport_candidates": destination_airports,
                },
            )

        if not shutil.which("trvl"):
            search_query = (
                f"Flights from {params.origin.strip()} "
                f"to {params.destination.strip()} on {params.date}"
            )
            search_url = (
                "https://www.google.com/travel/flights?"
                f"q={quote_plus(search_query)}"
            )
            return ToolResult(
                success=True,
                message=(
                    "Live flight inventory is unavailable in this "
                    "deployment. Use the flight search link to check "
                    "current schedules and prices."
                ),
                data={
                    "type": "flight_list",
                    "items": [],
                    "search_url": search_url,
                    "live_inventory": False,
                },
            )

        try:
            result = subprocess.run(
                [
                    "trvl",
                    "flights",
                    origin_iata,
                    dest_iata,
                    params.date,
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30.0,
            )

            data = json.loads(result.stdout)

            flights = (
                data
                if isinstance(data, list)
                else (
                    data.get("flights")
                    or data.get("results")
                    or []
                )
            )

            valid = []

            for flight in flights:
                legs = flight.get("legs", [])

                if not legs:
                    continue

                if (
                    legs[0].get("departure_airport", {}).get(
                        "code", ""
                    ) == origin_iata
                    and legs[-1].get("arrival_airport", {}).get(
                        "code", ""
                    ) == dest_iata
                ):
                    valid.append(flight)

            if not valid:
                return ToolResult(
                    success=True,
                    message=(
                        f"No live flights were returned from "
                        f"{origin_iata} to {dest_iata}. "
                        "Check the external search for other options."
                    ),
                    data={
                        "type": "flight_list",
                        "items": [],
                        "search_url": _flight_search_url(params),
                        "live_inventory": True,
                        "resolution_status": "no_results",
                        "origin_airport": origin_airports[0],
                        "destination_airport": destination_airports[0],
                        "origin_airport_candidates": origin_airports,
                        "destination_airport_candidates": destination_airports,
                    },
                )

            structured = []

            for flight in valid[:3]:
                legs = flight.get("legs", [])

                try:
                    raw_price = float(flight.get("price", 0))
                except (TypeError, ValueError):
                    raw_price = 0.0

                raw_cur = str(flight.get("currency") or "").upper().strip()
                display_price = (
                    format_price(raw_price, raw_cur)
                    if raw_price > 0 and raw_cur
                    else "Price unavailable"
                )

                segments = [
                    {
                        "airline": leg.get("airline", "Unknown"),
                        "flight_number": leg.get(
                            "flight_number",
                            "N/A",
                        ),
                        "origin": leg.get(
                            "departure_airport", {}
                        ).get("code", ""),
                        "destination": leg.get(
                            "arrival_airport", {}
                        ).get("code", ""),
                        "departure": leg.get(
                            "departure_time", ""
                        ).replace("T", " ")[:16],
                        "arrival": leg.get(
                            "arrival_time", ""
                        ).replace("T", " ")[:16],
                    }
                    for leg in legs
                ]

                booking_url = flight.get("booking_url", "")

                if not booking_url:
                    booking_url = (
                        "https://www.google.com/travel/flights?"
                        f"q=Flights%20from%20{origin_iata}%20"
                        f"to%20{dest_iata}%20on%20{params.date}"
                    )

                structured.append(
                    {
                        "price": display_price,
                        "currency": raw_cur or None,
                        "segments": segments,
                        "stops": len(segments) - 1,
                        "url": booking_url,
                    }
                )

            return ToolResult(
                success=True,
                message=(
                    f"Found {len(structured)} flight option(s)."
                ),
                data={
                    "type": "flight_list",
                    "items": structured,
                    "origin_airport": origin_airports[0],
                    "destination_airport": destination_airports[0],
                    "origin_airport_candidates": origin_airports,
                    "destination_airport_candidates": destination_airports,
                },
            )

        except Exception as e:
            return ToolResult(
                success=True,
                message=(
                    "The live flight provider could not complete the search. "
                    "No live flight results are available; use the external "
                    "search link to check current schedules and prices."
                ),
                data={
                    "type": "flight_list",
                    "items": [],
                    "search_url": _flight_search_url(params),
                    "live_inventory": False,
                    "resolution_status": "provider_unavailable",
                    "provider_error": str(e),
                    "origin_airport": origin_airports[0],
                    "destination_airport": destination_airports[0],
                    "origin_airport_candidates": origin_airports,
                    "destination_airport_candidates": destination_airports,
                },
            )


# ─── HOTELS ────────────────────────────────────────────────


def _flight_search_url(params) -> str:
    query = (
        f"Flights from {params.origin.strip()} "
        f"to {params.destination.strip()} on {params.date}"
    )
    return (
        "https://www.google.com/travel/flights?"
        f"q={quote_plus(query)}"
    )


def _hotel_search_url(params) -> str:
    return (
        "https://www.booking.com/searchresults.html"
        f"?ss={quote_plus(params.city)}"
        f"&checkin={params.check_in}"
        f"&checkout={params.check_out}"
        f"&group_adults={max(1, params.travellers)}"
        "&no_rooms=1"
    )


class HotelInput(BaseModel):
    city: str = Field(...)
    check_in: str = Field(...)
    check_out: str = Field(...)
    travellers: int = Field(default=2)
    budget: Optional[float] = Field(default=None)


class StayApiHotelTool(BaseTool):
    name = "search_hotels_stayapi"

    description = (
        "Search hotels and return external Booking.com links. "
        "Does not create a reservation or process payment. "
        "Budget is MAXIMUM TOTAL price for the entire stay."
    )

    input_schema = HotelInput
    requires_confirmation = False

    capability = "travel"

    provider_adapters = (
        {
            "provider_id": "trvl_cli",
            "display_name": "TRVL CLI adapter",
        },
    )

    supported_operations = ("search",)

    def execute(
        self,
        ctx: ToolContext,
        params: HotelInput,
    ) -> ToolResult:

        # Validate stay dates before making any external provider call.
        try:
            check_in = datetime.strptime(
                params.check_in,
                "%Y-%m-%d",
            ).date()

            check_out = datetime.strptime(
                params.check_out,
                "%Y-%m-%d",
            ).date()

            if check_in.isoformat() != params.check_in:
                raise ValueError(
                    "Check-in must use YYYY-MM-DD format."
                )

            if check_out.isoformat() != params.check_out:
                raise ValueError(
                    "Check-out must use YYYY-MM-DD format."
                )

            if check_out <= check_in:
                raise ValueError(
                    "Check-out must be after check-in."
                )

        except (TypeError, ValueError) as exc:
            return ToolResult(
                success=False,
                message=(
                    f"Hotel search skipped: invalid stay dates. {exc}"
                ),
            )

        cli_city = normalize_cli_city(params.city)

        if not shutil.which("trvl"):
            search_url = (
                "https://www.booking.com/searchresults.html"
                f"?ss={quote_plus(params.city)}"
                f"&checkin={params.check_in}"
                f"&checkout={params.check_out}"
                f"&group_adults={max(1, params.travellers)}"
                "&no_rooms=1"
            )
            return ToolResult(
                success=True,
                message=(
                    f"Live hotel inventory is unavailable in this "
                    f"deployment for {params.city}. You can check "
                    "current hotel availability and prices using "
                    "the booking search link."
                ),
                data={
                    "type": "hotel_list",
                    "items": [],
                    "search_url": search_url,
                    "live_inventory": False,
                },
            )

        try:
            result = subprocess.run(
                [
                    "trvl",
                    "hotels",
                    cli_city,
                    "--checkin",
                    params.check_in,
                    "--checkout",
                    params.check_out,
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=90.0,
            )

        except Exception as e:
            return ToolResult(
                success=True,
                message=(
                    f"The live hotel provider could not complete the search "
                    f"for {params.city}. No live hotel results are available. "
                    "Use the external search link to check current prices."
                ),
                data={
                    "type": "hotel_list",
                    "items": [],
                    "search_url": _hotel_search_url(params),
                    "live_inventory": False,
                    "resolution_status": "provider_unavailable",
                    "provider_error": str(e),
                },
            )

        try:
            data = json.loads(result.stdout)

            hotels = (
                data
                if isinstance(data, list)
                else (
                    data.get("hotels")
                    or data.get("results")
                    or []
                )
            )

        except json.JSONDecodeError as e:
            return ToolResult(
                success=True,
                message=(
                    "The hotel provider returned unreadable data. "
                    "No live hotel results are available; use the external "
                    "search link to check current availability."
                ),
                data={
                    "type": "hotel_list",
                    "items": [],
                    "search_url": _hotel_search_url(params),
                    "live_inventory": False,
                    "resolution_status": "invalid_provider_response",
                    "provider_error": str(e),
                },
            )

        if not hotels:
            return ToolResult(
                success=True,
                message=(
                    f"The provider returned no hotels in {params.city} "
                    "for those dates. Check the external search for "
                    "additional availability."
                ),
                data={
                    "type": "hotel_list",
                    "items": [],
                    "search_url": _hotel_search_url(params),
                    "live_inventory": True,
                    "resolution_status": "no_results",
                },
            )

        try:
            d1 = datetime.strptime(
                params.check_in,
                "%Y-%m-%d",
            )

            d2 = datetime.strptime(
                params.check_out,
                "%Y-%m-%d",
            )

            nights = max(1, (d2 - d1).days)

        except Exception:
            nights = 1

        candidates = []
        excluded = 0

        for hotel in hotels:
            name = (hotel.get("name") or "").strip()

            if not name:
                continue

            try:
                raw_price = float(hotel.get("price", 0))
            except (TypeError, ValueError):
                continue

            raw_cur = str(hotel.get("currency") or "").upper().strip()

            if raw_price <= 0 or not raw_cur:
                continue

            total_amount = raw_price * nights
            total_inr = total_amount if raw_cur == "INR" else None

            if (
                params.budget is not None
                and total_inr is not None
                and total_inr > params.budget
            ):
                excluded += 1
                continue

            slug = re.sub(
                r"[^a-zA-Z0-9\s-]",
                "",
                name,
            ).strip().lower().replace(" ", "-")

            booking_url = (
                "https://www.booking.com/searchresults.html"
                f"?ss={slug}+{quote_plus(params.city)}"
                f"&checkin={params.check_in}"
                f"&checkout={params.check_out}"
                f"&group_adults={params.travellers}"
                "&no_rooms=1"
            )

            candidates.append(
                {
                    "name": name,
                    "address": hotel.get("address", ""),
                    "price_per_night": format_price(
                        raw_price,
                        raw_cur,
                    ),
                    "total_stay": format_price(
                        total_amount,
                        raw_cur,
                    ),
                    "currency": raw_cur,
                    "nights": nights,
                    "total_inr": total_inr,
                    "booking_url": booking_url,
                    "image_url": (
                        hotel.get("image_url")
                        or hotel.get("photo_url")
                        or hotel.get("thumbnail")
                        or (
                            hotel.get("image", {}).get("url")
                            if isinstance(
                                hotel.get("image"),
                                dict,
                            )
                            else hotel.get("image")
                        )
                        or ""
                    ),
                    "rating": (
                        hotel.get("rating")
                        or hotel.get("review_score")
                        or ""
                    ),
                }
            )

        if not candidates:
            msg = (
                f"I couldn't find any hotels in {params.city} "
                f"for those dates"
            )

            if excluded > 0:
                msg += (
                    f" within ₹{params.budget:,.0f} total "
                    f"for {nights} nights "
                    f"(all {excluded} exceeded budget)."
                )
            else:
                msg += "."

            return ToolResult(
                success=True,
                message=msg + " You can also check the external booking search.",
                data={
                    "type": "hotel_list",
                    "items": [],
                    "search_url": _hotel_search_url(params),
                    "live_inventory": True,
                    "resolution_status": (
                        "budget_filtered" if excluded > 0 else "no_usable_results"
                    ),
                },
            )

        # Provider order is retained because prices in different
        # currencies are not directly comparable.
        top = candidates[:3]

        msg = (
            f"Found {len(top)} hotels in {params.city} "
            f"for {nights} nights"
        )

        if params.budget and all(
            item["currency"] == "INR" for item in top
        ):
            msg += (
                f" within your ₹{params.budget:,.0f} budget"
            )

        msg += "."

        return ToolResult(
            success=True,
            message=msg,
            data={
                "type": "hotel_list",
                "items": top,
            },
        )


# ─── GEOAPIFY PLACES ───────────────────────────────────────


class PlacesInput(BaseModel):
    location: Optional[str] = Field(default=None)
    category: str = Field(default="restaurant")
    query: Optional[str] = Field(default=None)


class GeoapifyPlacesTool(BaseTool):
    name = "search_places_geoapify"

    description = "Find real places and restaurants via Geoapify."

    input_schema = PlacesInput
    requires_confirmation = False

    capability = "place_discovery"

    provider_adapters = (
        {
            "provider_id": "geoapify",
            "display_name": "Geoapify",
        },
    )

    supported_operations = ("search",)

    def execute(
        self,
        ctx: ToolContext,
        params: PlacesInput,
    ) -> ToolResult:

        if not settings.geoapify_api_key:
            return ToolResult(
                success=False,
                message="Missing API Key",
            )

        final_location = params.location or params.query

        if not final_location:
            return ToolResult(
                success=False,
                message="Specify a location.",
            )

        try:
            geo_url = (
                "https://api.geoapify.com/v1/geocode/search?"
                f"text={quote(final_location)}"
                f"&limit=1&apiKey={settings.geoapify_api_key}"
            )

            with httpx.Client(timeout=10.0) as client:
                geo_res = client.get(geo_url).json()

                if not geo_res.get("features"):
                    return ToolResult(
                        success=False,
                        message=(
                            f"Location '{final_location}' not found."
                        ),
                    )

                feature = geo_res["features"][0]

                lat = feature["properties"]["lat"]
                lon = feature["properties"]["lon"]

                city_name = feature["properties"].get(
                    "city",
                    final_location,
                )

                cat = (
                    "catering.cafe"
                    if "cafe" in params.category.lower()
                    else "catering.restaurant"
                )

                places_url = (
                    "https://api.geoapify.com/v2/places?"
                    f"categories={cat}"
                    f"&filter=circle:{lon},{lat},10000"
                    "&limit=10"
                    f"&apiKey={settings.geoapify_api_key}"
                )

                places_res = client.get(places_url).json()

            valid_places = [
                {
                    "name": place["properties"].get(
                        "name",
                        "Unknown",
                    ),
                    "address": place["properties"].get(
                        "address_line2",
                        "",
                    ),
                    "map_url": (
                        "https://maps.google.com/?q="
                        + quote(
                            place["properties"].get("name", "")
                        )
                    ),
                }
                for place in places_res.get("features", [])
                if place["properties"].get("name")
            ]

            if not valid_places:
                return ToolResult(
                    success=True,
                    message="No places found.",
                )

            return ToolResult(
                success=True,
                message=f"Top places in {city_name}.",
                data={
                    "type": "place_list",
                    "items": valid_places[:5],
                    "city": city_name,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Search error: {e}",
            )


# ─── CAB ────────────────────────────────────────────────────


class CabInput(BaseModel):
    pickup_location: str = Field(
        ...,
        description="The pickup location explicitly supplied or confirmed by the user.",
    )

    dropoff_location: str = Field(
        ...,
        description="The drop-off location explicitly supplied or confirmed by the user.",
    )



class CabDeepLinkTool(BaseTool):
    name = "get_cab_links"

    description = (
        "Generate Uber/Ola ride handoff links for the user to "
        "review and book in the provider app. "
        "Does not request a ride or process payment."
    )

    input_schema = CabInput
    requires_confirmation = False
    is_mutating = False
    capability = "transport"

    provider_adapters = (
        {
            "provider_id": "uber",
            "display_name": "Uber",
        },
        {
            "provider_id": "ola",
            "display_name": "Ola",
        },
    )

    supported_operations = ("link_generation",)

    @staticmethod
    def _provider_url(
        provider_id: str,
        params: CabInput,
    ) -> str:
        if provider_id == "uber":
            return (
                "https://m.uber.com/ul/?action=setPickup"
                "&pickup[formatted_address]="
                + quote(params.pickup_location, safe="")
                + "&dropoff[formatted_address]="
                + quote(params.dropoff_location, safe="")
            )

        if provider_id == "ola":
            return (
                "https://book.olacabs.com/?pickup_name={}&drop_name={}"
                .format(
                    quote(params.pickup_location),
                    quote(params.dropoff_location),
                )
            )

        raise ValueError(f"Unsupported cab provider: {provider_id}")

    def execute(
        self,
        ctx: ToolContext,
        params: CabInput,
    ) -> ToolResult:
        uber = self._provider_url("uber", params)
        ola = self._provider_url("ola", params)

        return ToolResult(
            success=True,
            message=(
                f"Book a ride from {params.pickup_location} "
                f"to {params.dropoff_location}."
            ),
            data={
                "type": "transport_links",
                "origin": params.pickup_location,
                "destination": params.dropoff_location,
                "links": {
                    "uber": uber,
                    "ola": ola,
                },
            },
        )

    def execute_for_provider(
        self,
        ctx: ToolContext,
        params: CabInput,
        provider_id: str,
    ) -> ToolResult:
        provider_id = str(provider_id).lower()

        try:
            url = self._provider_url(provider_id, params)
        except ValueError as exc:
            return ToolResult(
                success=False,
                message=str(exc),
            )

        return ToolResult(
            success=True,
            message=(
                f"Generated a {provider_id.capitalize()} ride handoff "
                f"link from {params.pickup_location} "
                f"to {params.dropoff_location}. "
                "Review and confirm the ride in the provider app."
            ),
            data={
                "type": "transport_links",
                "origin": params.pickup_location,
                "destination": params.dropoff_location,
                "provider_id": provider_id,
                "links": {
                    provider_id: url,
                },
                "disclaimer": (
                    "This link does not book a ride or process payment. "
                    "Review and confirm the ride in the provider app."
                ),
            },
        )
