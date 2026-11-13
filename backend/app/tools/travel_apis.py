
"""Warik AI travel tools — flights, hotels, places, cabs."""

import httpx
import json
import subprocess
import re
import math

from urllib.parse import quote_plus, quote
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult
from app.core.config import settings


CITY_TO_IATA = {
    "MUMBAI": "BOM",
    "BOMBAY": "BOM",
    "NEW DELHI": "DEL",
    "DELHI": "DEL",
    "BANGALORE": "BLR",
    "BENGALURU": "BLR",
    "JAIPUR": "JAI",
    "KOLKATA": "CCU",
    "CHENNAI": "MAA",
    "GOA": "GOI",
    "PANAJI": "GOI",
    "HYDERABAD": "HYD",
    "PUNE": "PNQ",
    "AHMEDABAD": "AMD",
    "KOCHI": "COK",
    "LUCKNOW": "LKO",
    "CHANDIGARH": "IXC",
    "AGRA": "AGR",
    "VARANASI": "VNS",
    "AMRITSAR": "ATQ",
}


STATE_TO_CLI_CITY = {
    "goa": "Panaji",
    "kerala": "Kochi",
    "rajasthan": "Jaipur",
    "west bengal": "Kolkata",
    "maharashtra": "Mumbai",
    "punjab": "Amritsar",
    "tamil nadu": "Chennai",
    "karnataka": "Bangalore",
    "uttar pradesh": "Lucknow",
    "himachal pradesh": "Shimla",
    "delhi": "New Delhi",
}


def get_iata(city: str) -> str:
    if not isinstance(city, str):
        return ""

    normalized = city.upper().strip()
    return CITY_TO_IATA.get(normalized, normalized)


def normalize_cli_city(city: str) -> str:
    return STATE_TO_CLI_CITY.get(city.lower().strip(), city)


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

        origin_iata = get_iata(params.origin)
        dest_iata = get_iata(params.destination)

        # Never invoke the provider with unresolved LLM placeholders
        # or malformed airport/date values.
        if not re.fullmatch(r"[A-Z]{3}", origin_iata):
            return ToolResult(
                success=False,
                message=(
                    "Flight search skipped: "
                    "a valid departure airport is required."
                ),
            )

        if not re.fullmatch(r"[A-Z]{3}", dest_iata):
            return ToolResult(
                success=False,
                message=(
                    "Flight search skipped: "
                    "a valid destination airport is required."
                ),
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
                        f"No flights found from {origin_iata} "
                        f"to {dest_iata}."
                    ),
                )

            structured = []

            for flight in valid[:3]:
                legs = flight.get("legs", [])

                raw_price = float(flight.get("price", 0))
                raw_cur = flight.get("currency", "EUR").upper()

                rate = (
                    90.0
                    if raw_cur == "EUR"
                    else 83.0
                    if raw_cur == "USD"
                    else 1.0
                )

                price_inr = raw_price * rate

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
                        "price": format_price(
                            price_inr,
                            "INR",
                        ),
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
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Flight search unavailable: {e}",
            )


# ─── HOTELS ────────────────────────────────────────────────


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
                success=False,
                message=(
                    f"Hotel provider error for {params.city}: {e}"
                ),
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

        except json.JSONDecodeError:
            return ToolResult(
                success=False,
                message=(
                    "Hotel provider returned unreadable data."
                ),
            )

        if not hotels:
            return ToolResult(
                success=True,
                message=(
                    f"No hotels found in {params.city} "
                    "for those dates."
                ),
                data={
                    "type": "hotel_list",
                    "items": [],
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

            raw_price = float(hotel.get("price", 0))
            raw_cur = hotel.get("currency", "EUR").upper()

            if raw_price <= 0:
                continue

            rate = (
                90.0
                if raw_cur == "EUR"
                else 83.0
                if raw_cur == "USD"
                else 1.0
            )

            per_night_inr = raw_price * rate
            total_inr = per_night_inr * nights

            if params.budget and total_inr > params.budget:
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
                        per_night_inr,
                        "INR",
                    ),
                    "total_stay": format_price(
                        total_inr,
                        "INR",
                    ),
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
                msg += " with verified pricing."

            return ToolResult(
                success=True,
                message=msg,
                data={
                    "type": "hotel_list",
                    "items": [],
                },
            )

        candidates.sort(
            key=lambda item: item["total_inr"]
        )

        top = candidates[:3]

        msg = (
            f"Found {len(top)} hotels in {params.city} "
            f"for {nights} nights"
        )

        if params.budget:
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
