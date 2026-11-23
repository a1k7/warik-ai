
"""Warik AI travel tools — flights, hotels, places, cabs."""

import httpx
import json
import subprocess
import shutil
import re
import math

from urllib.parse import quote_plus, quote, urlparse
from typing import Literal, Optional

from app.integrations.serpapi.client import SerpApiError, serpapi_client
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
    """Validated flight search constraints passed to Google Flights/SerpApi."""

    origin: str = Field(..., min_length=2, max_length=120)
    destination: str = Field(..., min_length=2, max_length=120)
    date: str = Field(...)
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    # SerpApi Google Flights cabin values: 1 economy, 2 premium economy,
    # 3 business, 4 first.
    travel_class: int = Field(default=1, ge=1, le=4)
    # Maximum number of stops accepted by the user: 0, 1, or 2.
    max_stops: int | None = Field(default=None, ge=0, le=2)
    currency: str = Field(default="INR", min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    outbound_times: str | None = Field(
        default=None,
        pattern=r"^(?:[0-9]|1[0-9]|2[0-3]),(?:[0-9]|1[0-9]|2[0-3])(?:,(?:[0-9]|1[0-9]|2[0-3]),(?:[0-9]|1[0-9]|2[0-3]))?$",
    )
    # Retain compatibility with mission extraction and older callers.
    direct_only: bool | None = None



def _normalise_serpapi_flights(
    payload: dict,
    origin_iata: str,
    destination_iata: str,
    fallback_url: str,
) -> tuple[list[dict], str]:
    """Normalize only price-bearing itineraries with a verified airport chain."""
    metadata = payload.get("search_metadata") or {}
    search_parameters = payload.get("search_parameters") or {}
    provider_url = metadata.get("google_flights_url")
    parsed_url = urlparse(provider_url or "")
    search_url = (
        provider_url
        if parsed_url.scheme == "https"
        and parsed_url.hostname in {"google.com", "www.google.com"}
        else fallback_url
    )

    def airport_codes(value: str) -> set[str]:
        return {
            token.strip().upper()
            for token in str(value or "").split(",")
            if len(token.strip()) == 3 and token.strip().isalpha()
        }

    requested_origins = airport_codes(origin_iata)
    requested_destinations = airport_codes(destination_iata)
    currency = str(search_parameters.get("currency") or "INR").upper().strip()
    if not currency or len(currency) != 3 or not currency.isalpha():
        currency = "INR"
    retrieved_at = metadata.get("created_at")
    candidates = (
        (payload.get("best_flights") or [])
        + (payload.get("other_flights") or [])
    )

    structured: list[dict] = []
    seen: set[tuple] = set()
    for flight in candidates:
        if not isinstance(flight, dict):
            continue
        raw_segments = flight.get("flights") or []
        if not isinstance(raw_segments, list) or not raw_segments:
            continue

        chain: list[dict] = []
        valid_chain = True
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                valid_chain = False
                break
            departure_airport = raw_segment.get("departure_airport") or {}
            arrival_airport = raw_segment.get("arrival_airport") or {}
            origin_code = str(departure_airport.get("id") or "").strip().upper()
            destination_code = str(arrival_airport.get("id") or "").strip().upper()
            if (
                len(origin_code) != 3 or not origin_code.isalpha()
                or len(destination_code) != 3 or not destination_code.isalpha()
            ):
                valid_chain = False
                break
            chain.append({
                "airline": raw_segment.get("airline") or "Unknown",
                "flight_number": raw_segment.get("flight_number") or "N/A",
                "origin": origin_code,
                "destination": destination_code,
                "departure": str(departure_airport.get("time") or "").replace("T", " ")[:16],
                "arrival": str(arrival_airport.get("time") or "").replace("T", " ")[:16],
                "duration_minutes": raw_segment.get("duration"),
            })

        if not valid_chain or not chain:
            continue
        if chain[0]["origin"] not in requested_origins:
            continue
        if chain[-1]["destination"] not in requested_destinations:
            continue
        # Every connecting segment must depart from the prior segment's
        # arrival airport. This rejects stitched or disconnected itineraries.
        if any(
            chain[index - 1]["destination"] != chain[index]["origin"]
            for index in range(1, len(chain))
        ):
            continue

        try:
            raw_price = float(flight.get("price"))
        except (TypeError, ValueError):
            continue
        if not (raw_price > 0 and math.isfinite(raw_price)):
            continue

        identity = (
            tuple((item["origin"], item["destination"], item["flight_number"], item["departure"]) for item in chain),
            raw_price,
            currency,
        )
        if identity in seen:
            continue
        seen.add(identity)

        raw_layovers = flight.get("layovers") or []
        layovers = []
        if isinstance(raw_layovers, list):
            for stop in raw_layovers:
                if not isinstance(stop, dict):
                    continue
                layovers.append({
                    "id": str(stop.get("id") or "").upper() or None,
                    "name": stop.get("name"),
                    "duration": stop.get("duration"),
                })

        structured.append({
            "price": format_price(raw_price, currency),
            "price_amount": raw_price,
            "currency": currency,
            "segments": chain,
            "stops": len(chain) - 1,
            "layovers": layovers,
            "url": search_url,
            "provider": "serpapi_google_flights",
            "source": "Google Flights via SerpApi",
            "retrieved_at": retrieved_at,
        })

    # Numeric sorting is essential: lexical sorting misorders e.g. 150,000
    # and 25,000 when display strings contain currency symbols and separators.
    structured.sort(key=lambda item: item["price_amount"])
    return structured[:10], search_url



def _serpapi_flight_search_params(params: FlightInput, origin_iata: str, dest_iata: str) -> dict:
    """Build SerpApi parameters from the validated FlightInput contract."""
    if params.max_stops is not None:
        # SerpApi: 1=nonstop, 2=up to one stop, 3=up to two stops.
        stops = str(params.max_stops + 1)
    elif params.direct_only is False:
        # Legacy explicit opt-in: allow any number of stops.
        stops = "0"
    else:
        stops = "1"

    request = {
        "engine": "google_flights",
        "departure_id": origin_iata,
        "arrival_id": dest_iata,
        "outbound_date": params.date,
        "type": "2",
        "stops": stops,
        "sort_by": "2",
        "currency": params.currency.upper(),
        "gl": "in",
        "hl": "en",
        "adults": str(params.adults),
        "children": str(params.children),
        "travel_class": str(params.travel_class),
    }
    if params.outbound_times:
        request["outbound_times"] = params.outbound_times
    return request


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
            "provider_id": "serpapi_google_flights",
            "display_name": "SerpApi Google Flights",
            "requires_auth": True,
        },
        {
            "provider_id": "trvl_cli",
            "display_name": "TRVL CLI adapter",
        },
    )

    supported_operations = ("search",)

    def execute(self, ctx: ToolContext, params: FlightInput, *, provider_id: str | None = None) -> ToolResult:

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

        # Prefer live Google Flights via SerpApi. If unavailable, retain
        # the existing TRVL CLI fallback below.
        serpapi_error = None
        if provider_id != "trvl_cli":
            try:
                serpapi_payload = serpapi_client.search(_serpapi_flight_search_params(params, origin_iata, dest_iata))

                structured, search_url = _normalise_serpapi_flights(
                    serpapi_payload,
                    origin_iata,
                    dest_iata,
                    _flight_search_url(params),
                )

                if not structured:
                    return ToolResult(
                        success=True,
                        message=(
                            f"No verified flights were returned from "
                            f"{origin_iata} to {dest_iata} for {params.date}. "
                            "You can check other options using the external search."
                        ),
                        data={
                            "type": "flight_list",
                            "items": [],
                            "search_url": search_url,
                            "live_inventory": True,
                            "resolution_status": "no_results",
                            "provider": "serpapi_google_flights",
                        "retrieved_at": (serpapi_payload.get("search_metadata") or {}).get("created_at"),
                        "provider_metadata": {
                            "search_id": (serpapi_payload.get("search_metadata") or {}).get("id"),
                            "status": (serpapi_payload.get("search_metadata") or {}).get("status"),
                            "created_at": (serpapi_payload.get("search_metadata") or {}).get("created_at"),
                            "google_flights_url": search_url,
                        },
                            "origin_airport": origin_airports[0],
                            "destination_airport": destination_airports[0],
                            "origin_airport_candidates": origin_airports,
                            "destination_airport_candidates": destination_airports,
                        },
                    )

                return ToolResult(
                    success=True,
                    message=f"Found {len(structured)} live flight option(s) via Google Flights.",
                    data={
                        "type": "flight_list",
                        "items": structured,
                        "search_url": search_url,
                        "live_inventory": True,
                        "resolution_status": "success",
                        "provider": "serpapi_google_flights",
                        "retrieved_at": (serpapi_payload.get("search_metadata") or {}).get("created_at"),
                        "provider_metadata": {
                            "search_id": (serpapi_payload.get("search_metadata") or {}).get("id"),
                            "status": (serpapi_payload.get("search_metadata") or {}).get("status"),
                            "created_at": (serpapi_payload.get("search_metadata") or {}).get("created_at"),
                            "google_flights_url": search_url,
                        },
                        "origin_airport": origin_airports[0],
                        "destination_airport": destination_airports[0],
                        "origin_airport_candidates": origin_airports,
                        "destination_airport_candidates": destination_airports,
                    },
                )

            except SerpApiError as exc:
                serpapi_error = str(exc)

            except Exception as exc:
                # Do not let an unexpected adapter error break the existing fallback.
                serpapi_error = f"SerpApi adapter error ({type(exc).__name__})."

        if provider_id == "serpapi_google_flights":
            return ToolResult(
                success=False,
                message="The explicitly selected SerpApi flight search failed; no other provider was substituted.",
                data={"type": "flight_list", "items": [], "provider": "serpapi_google_flights", "live_inventory": False, "resolution_status": "provider_unavailable"},
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
                    "Live flight providers could not complete the search. "
                    "Use the external search link to check current schedules "
                    "and prices."
                ),
                data={
                    "type": "flight_list",
                    "items": [],
                    "search_url": search_url,
                    "live_inventory": False,
                    "resolution_status": "provider_unavailable",
                    "provider_error": serpapi_error,
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
                        "duration_minutes": leg.get("duration_minutes") or leg.get("duration"),
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
                        "duration_minutes": flight.get("duration_minutes") or flight.get("duration"),
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

    def execute_for_provider(self, ctx: ToolContext, params: FlightInput, provider_id: str) -> ToolResult:
        """Execute only the explicitly selected flight provider."""
        if provider_id not in {"serpapi_google_flights", "trvl_cli"}:
            return ToolResult(False, f"Unsupported flight provider: {provider_id}", {"live_inventory": False})
        result = self.execute(ctx, params, provider_id=provider_id)
        data = dict(result.data or {})
        if result.success and data.get("live_inventory") is False and not data.get("items"):
            return ToolResult(False, f"Selected provider {provider_id} returned no live inventory.", data)
        if result.success:
            # Provider payload identity wins only when it matches the pinned adapter.
            data["provider"] = provider_id
            result.data = data
        return result


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
            "provider_id": "stayapi_booking",
            "display_name": "StayAPI hotel inventory",
            "requires_auth": True,
        },
        {
            "provider_id": "trvl_cli",
            "display_name": "TRVL CLI fallback",
        },
    )

    supported_operations = ("search",)

    def execute(self, ctx: ToolContext, params: HotelInput, *, provider_id: str | None = None) -> ToolResult:

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

        # Prefer direct StayAPI inventory when configured. The existing TRVL CLI
        # remains a fallback, so this does not remove any current provider path.
        from app.core.config import settings
        from app.integrations.stayapi.client import StayAPIClient, StayAPIError

        stayapi_key = str(getattr(settings, "stayapi_key", "") or "").strip()
        if provider_id == "stayapi_booking" and not stayapi_key:
            return ToolResult(
                success=False,
                message="StayAPI was selected, but its API key is not configured.",
                data={"type": "hotel_list", "items": [], "provider": "stayapi_booking", "live_inventory": False, "resolution_status": "provider_unavailable"},
            )
        if provider_id != "trvl_cli" and stayapi_key:
            try:
                stayapi_result = StayAPIClient(
                    stayapi_key,
                    timeout_seconds=25.0,
                ).search_hotels(
                    city=params.city,
                    check_in=params.check_in,
                    check_out=params.check_out,
                    adults=max(1, params.travellers),
                    rooms=1,
                    currency="INR",
                    language="en-us",
                    market="IN",
                    limit=25,
                )
                stayapi_items = stayapi_result["items"]
                excluded_stayapi = 0
                if params.budget is not None:
                    filtered = []
                    for item in stayapi_items:
                        amount_inr = item.get("total_inr")
                        if amount_inr is not None and amount_inr > params.budget:
                            excluded_stayapi += 1
                            continue
                        filtered.append(item)
                    stayapi_items = filtered

                if stayapi_items:
                    top = stayapi_items[:5]
                    for item in top:
                        amount = item.get("total_stay_amount")
                        currency = item.get("currency") or "INR"
                        if amount is not None:
                            item["total_stay"] = format_price(float(amount), currency)
                            item["price_per_night_display"] = format_price(
                                float(amount) / max(1, item.get("nights", 1)), currency
                            )
                    return ToolResult(
                        success=True,
                        message=(
                            f"Found {len(top)} live StayAPI hotel option(s) in {params.city}. "
                            "Prices are provider-reported total-stay amounts; verify the final rate and taxes before booking."
                        ),
                        data={
                            "type": "hotel_list",
                            "items": top,
                            "provider": "stayapi_booking",
                            "live_inventory": True,
                            "retrieved_at": stayapi_result.get("retrieved_at"),
                            "destination": stayapi_result.get("destination"),
                            "pagination": stayapi_result.get("pagination"),
                            "price_basis": "provider_min_total_price",
                            "excluded_over_budget_inr": excluded_stayapi,
                        },
                    )
                if stayapi_result["items"] and excluded_stayapi:
                    return ToolResult(
                        success=True,
                        message=(
                            f"StayAPI returned {excluded_stayapi} hotel(s), but all exceeded "
                            f"your INR {params.budget:,.0f} total-stay budget."
                        ),
                        data={
                            "type": "hotel_list",
                            "items": [],
                            "provider": "stayapi_booking",
                            "live_inventory": True,
                            "resolution_status": "budget_filtered",
                            "excluded_over_budget_inr": excluded_stayapi,
                            "search_url": _hotel_search_url(params),
                        },
                    )
                if not stayapi_result["items"]:
                    return ToolResult(
                        success=True,
                        message=f"StayAPI returned no available hotel results in {params.city} for those dates.",
                        data={
                            "type": "hotel_list",
                            "items": [],
                            "provider": "stayapi_booking",
                            "live_inventory": True,
                            "resolution_status": "no_results",
                            "retrieved_at": stayapi_result.get("retrieved_at"),
                            "search_url": _hotel_search_url(params),
                        },
                    )
            except (StayAPIError, ValueError) as exc:
                if provider_id == "stayapi_booking":
                    return ToolResult(
                        success=False,
                        message=f"Selected StayAPI search failed: {type(exc).__name__}.",
                        data={"type": "hotel_list", "items": [], "provider": "stayapi_booking", "live_inventory": False, "resolution_status": "provider_unavailable"},
                    )
                # Preserve legacy fallback only for non-pinned direct execution.
                pass

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

    def execute_for_provider(self, ctx: ToolContext, params: HotelInput, provider_id: str) -> ToolResult:
        """Execute only the explicitly selected hotel provider; never cross-fallback."""
        if provider_id not in {"stayapi_booking", "trvl_cli"}:
            return ToolResult(False, f"Unsupported hotel provider: {provider_id}", {"live_inventory": False})
        result = self.execute(ctx, params, provider_id=provider_id)
        data = dict(result.data or {})
        if result.success and data.get("live_inventory") is False and not data.get("items"):
            return ToolResult(False, f"Selected provider {provider_id} returned no live inventory.", data)
        if result.success:
            data.setdefault("provider", provider_id)
            # The legacy TRVL success payload did not set this field consistently.
            # A successful, parsed TRVL CLI response (including a genuine no-results
            # response) is a live inventory search; explicit False is preserved.
            if provider_id == "trvl_cli":
                data.setdefault("live_inventory", True)
            result.data = data
        return result


# ─── GEOAPIFY PLACES ───────────────────────────────────────


class PlacesInput(BaseModel):
    location: Optional[str] = Field(default=None)
    category: str = Field(default="restaurant")
    query: Optional[str] = Field(default=None)



class GeoapifyPlacesTool(BaseTool):
    name = "search_places_geoapify"
    description = "Find real places and restaurants using Geoapify or OpenStreetMap."
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
        final_location = params.location or params.query

        if not final_location:
            return ToolResult(
                success=False,
                message="Specify a location.",
            )

        category = (params.category or "").lower()
        kind = (
            "restaurant"
            if any(word in category for word in ("restaurant", "cafe", "food"))
            else "attraction"
        )

        # Geoapify is optional and preferred when configured.
        if settings.geoapify_api_key:
            try:
                with httpx.Client(timeout=10.0) as client:
                    geo_response = client.get(
                        "https://api.geoapify.com/v1/geocode/search",
                        params={
                            "text": final_location,
                            "limit": 1,
                            "apiKey": settings.geoapify_api_key,
                        },
                    )
                    geo_response.raise_for_status()
                    geo_data = geo_response.json()

                    features = geo_data.get("features", [])
                    if features:
                        props = features[0].get("properties", {})
                        lat = float(props["lat"])
                        lon = float(props["lon"])

                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            city_name = (
                                props.get("city")
                                or props.get("name")
                                or final_location
                            )

                            if kind == "restaurant":
                                cat = (
                                    "catering.cafe"
                                    if "cafe" in category
                                    else "catering.restaurant"
                                )
                            else:
                                cat = "tourism.attraction"

                            places_response = client.get(
                                "https://api.geoapify.com/v2/places",
                                params={
                                    "categories": cat,
                                    "filter": f"circle:{lon},{lat},10000",
                                    "limit": 10,
                                    "apiKey": settings.geoapify_api_key,
                                },
                            )
                            places_response.raise_for_status()
                            places_data = places_response.json()

                            valid_places = []
                            for place in places_data.get("features", []):
                                properties = place.get("properties", {})
                                name = str(properties.get("name") or "").strip()

                                if not name:
                                    continue

                                valid_places.append({
                                    "name": name,
                                    "address": (
                                        properties.get("address_line2")
                                        or properties.get("formatted")
                                        or ""
                                    ),
                                    "map_url": (
                                        "https://maps.google.com/?q=" + quote(name)
                                    ),
                                    "source": "Geoapify",
                                })

                            if valid_places:
                                return ToolResult(
                                    success=True,
                                    message=f"Places found in {city_name}.",
                                    data={
                                        "type": "place_list",
                                        "items": valid_places[:5],
                                        "city": city_name,
                                        "source": "Geoapify",
                                    },
                                )

            except (
                httpx.HTTPError,
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
            ):
                # Try OpenStreetMap instead of failing on Geoapify errors.
                pass

        # Resolve the location independently through Nominatim.
        try:
            candidates = geocoder().search(final_location, limit=5)
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Location geocoding provider unavailable: {exc}",
            )

        accepted_types = {
            "city",
            "town",
            "village",
            "municipality",
            "administrative",
        }
        resolved = None

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

            resolved = candidate
            break

        if resolved is None:
            return ToolResult(
                success=False,
                message=f"Could not verify location: {final_location}.",
            )

        # Search OpenStreetMap for real provider records.
        try:
            places = places_provider().search(
                resolved,
                kind=kind,
                limit=10,
                radius_m=10000,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Place discovery provider unavailable: {exc}",
            )

        valid_places = []

        for place in places:
            name = str(place.get("name") or "").strip()
            if not name:
                continue

            item = {
                **place,
                "name": name,
            }

            lat = place.get("lat")
            lon = place.get("lon")

            if lat is not None and lon is not None:
                item["map_url"] = (
                    f"https://www.openstreetmap.org/?mlat={lat}"
                    f"&mlon={lon}#map=16/{lat}/{lon}"
                )
            else:
                item["map_url"] = "https://www.openstreetmap.org/"

            valid_places.append(item)

        city_name = resolved.get("name") or final_location

        return ToolResult(
            success=True,
            message=(
                f"Places found in {city_name}."
                if valid_places
                else f"No places found in {city_name}."
            ),
            data={
                "type": "place_list",
                "items": valid_places[:5],
                "city": city_name,
                "source": "OpenStreetMap",
            },
        )


# ─── CAB ────────────────────────────────────────────────────


class CabInput(BaseModel):
    pickup_location: str = Field(
        ...,
        min_length=2,
        max_length=240,
        description="The pickup location explicitly supplied or confirmed by the user.",
    )
    dropoff_location: str = Field(
        ...,
        min_length=2,
        max_length=240,
        description="The drop-off location explicitly supplied or confirmed by the user.",
    )
    pickup_at: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Requested local pickup time in ISO format, or 'now'. Provider handoff may require manual scheduling.",
    )
    passengers: int = Field(default=1, ge=1, le=8)
    vehicle_preference: Literal["any", "mini", "sedan", "suv", "premium"] = "any"
    luggage_count: int = Field(default=0, ge=0, le=8)



class CabDeepLinkTool(BaseTool):
    name = "get_cab_links"

    description = (
        "Prepare Uber/Ola ride handoff links from explicitly supplied pickup "
        "and drop-off locations, preserving requested schedule, passenger, "
        "vehicle and luggage preferences. This is not a live fare search and "
        "does not request a ride or process payment."
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
                "pickup_at": params.pickup_at,
                "passengers": params.passengers,
                "vehicle_preference": params.vehicle_preference,
                "luggage_count": params.luggage_count,
                "links": {
                    "uber": uber,
                    "ola": ola,
                },
                "live_quote": False,
                "booking_created": False,
                "payment_processed": False,
                "handoff_fields": ["pickup_location", "dropoff_location"],
                "manual_review_fields": [
                    "pickup_at",
                    "passengers",
                    "vehicle_preference",
                    "luggage_count",
                ],
                "disclaimer": (
                    "These links prefill pickup and drop-off only. Confirm "
                    "live availability, fare, pickup time, passenger count "
                    "and vehicle preference inside the provider app. "
                    "No ride has been booked and no payment has been made."
                ),
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
                "pickup_at": params.pickup_at,
                "passengers": params.passengers,
                "vehicle_preference": params.vehicle_preference,
                "luggage_count": params.luggage_count,
                "provider_id": provider_id,
                "links": {
                    provider_id: url,
                },
                "live_quote": False,
                "booking_created": False,
                "payment_processed": False,
                "handoff_fields": ["pickup_location", "dropoff_location"],
                "manual_review_fields": [
                    "pickup_at",
                    "passengers",
                    "vehicle_preference",
                    "luggage_count",
                ],
                "disclaimer": (
                    "This link pre-fills pickup and drop-off only. Confirm "
                    "availability, fare, schedule and vehicle details in the "
                    "provider app. It does not create a booking or payment."
                ),
            },
        )
