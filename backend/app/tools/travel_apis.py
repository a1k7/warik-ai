
"""Warik AI travel tools — flights, hotels, places, cabs."""

import httpx
import json
import subprocess
import shutil
import re
import math

from urllib.parse import quote_plus, quote, urlparse
from typing import Optional
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    origin: str = Field(..., description="Departure city or verified airport code.")
    destination: str = Field(..., description="Arrival city or verified airport code.")
    date: str = Field(..., description="Local departure date in YYYY-MM-DD.")
    departure_time_from: Optional[str] = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Earliest acceptable departure time at the origin airport, local HH:MM.",
    )
    departure_time_to: Optional[str] = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Latest acceptable departure time at the origin airport, local HH:MM.",
    )
    arrival_time_from: Optional[str] = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Earliest acceptable arrival time at the destination airport, local HH:MM.",
    )
    arrival_time_to: Optional[str] = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Latest acceptable arrival time at the destination airport, local HH:MM.",
    )
    cabin_class: Optional[Literal["economy", "premium_economy", "business", "first"]] = Field(
        default=None,
        description="Requested cabin class, only when explicitly stated or saved in user preferences.",
    )
    stops: Optional[Literal["any", "nonstop", "1", "2"]] = Field(
        default=None,
        description="Maximum stop preference: nonstop, one stop, two stops, or any.",
    )
    sort_by: Optional[Literal["price", "departure_time"]] = Field(
        default=None,
        description="Optional ranking preference. If omitted, preserve provider ranking.",
    )
    passengers: int = Field(default=1, ge=1, le=9, description="Number of adult passengers.")

    @field_validator("departure_time_from", "departure_time_to", "arrival_time_from", "arrival_time_to")
    @classmethod
    def validate_time_window_value(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("Flight times must use 24-hour HH:MM format.") from exc
        return value



def _duffel_datetime(value: str | None) -> str | None:
    """Format a provider ISO timestamp for the current flight result UI."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)[:32]


def _duffel_offer_to_flight_item(offer: dict) -> dict | None:
    """Normalize a Duffel offer without inventing prices or booking URLs."""
    slices = offer.get("slices") or []
    if not slices or not isinstance(slices[0], dict):
        return None
    raw_segments = slices[0].get("segments") or []
    if not raw_segments:
        return None

    segments = []
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        origin = segment.get("origin") or {}
        destination = segment.get("destination") or {}
        operating = segment.get("operating_carrier") or {}
        marketing = segment.get("marketing_carrier") or {}
        carrier_name = operating.get("name") or marketing.get("name") or "Airline not supplied"
        segments.append({
            "airline": carrier_name,
            "operating_carrier": carrier_name,
            "flight_number": segment.get("marketing_carrier_flight_number") or segment.get("operating_carrier_flight_number") or "Not supplied",
            "origin": origin.get("iata_code") or origin.get("name") or "",
            "destination": destination.get("iata_code") or destination.get("name") or "",
            "departure": _duffel_datetime(segment.get("departing_at")),
            "arrival": _duffel_datetime(segment.get("arriving_at")),
            "origin_airport_name": origin.get("name"),
            "destination_airport_name": destination.get("name"),
            "origin_terminal": segment.get("origin_terminal"),
            "destination_terminal": segment.get("destination_terminal"),
        })
    if not segments:
        return None

    amount = offer.get("total_amount")
    currency = str(offer.get("total_currency") or "").upper()
    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError):
        numeric_amount = None
    price = (
        format_price(numeric_amount, currency)
        if numeric_amount is not None and numeric_amount > 0 and currency
        else "Price unavailable"
    )
    owner = offer.get("owner") or {}
    return {
        "offer_id": offer.get("id"),
        "price": price,
        "amount": numeric_amount,
        "currency": currency or None,
        "departure_time": segments[0]["departure"],
        "arrival_time": segments[-1]["arrival"],
        "segments": segments,
        "stops": max(0, len(segments) - 1),
        "operating_carrier": segments[0]["operating_carrier"],
        "owner": owner.get("name"),
        "expires_at": offer.get("expires_at"),
        "live_mode": offer.get("live_mode"),
    }

class RealFlightSearchTool(BaseTool):
    name = "search_flights_real"

    description = (
        "Search current flight offers using the configured provider. Returns live offer details when available. "
        "Does not create a booking, issue a ticket, or process payment."
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

    def __init__(self):
        # Expose the configured flight provider in the live tool manifest.
        if settings.duffel_api_key.strip():
            self.provider_adapters = ({"provider_id": "duffel", "display_name": "Duffel"},)
        else:
            self.provider_adapters = ({"provider_id": "trvl_cli", "display_name": "TRVL CLI adapter"},)

    def execute(self, ctx: ToolContext, params: FlightInput) -> ToolResult:
        if settings.duffel_api_key.strip():
            return self._search_duffel(params)
        return self._execute_trvl_cli(ctx, params)

    def execute_for_provider(self, ctx: ToolContext, params: FlightInput, provider_id: str) -> ToolResult:
        provider_id = str(provider_id).strip().lower()
        if provider_id == "duffel" and settings.duffel_api_key.strip():
            return self._search_duffel(params)
        if provider_id == "trvl_cli" and not settings.duffel_api_key.strip():
            return self._execute_trvl_cli(ctx, params)
        return ToolResult(success=False, message=f"Flight provider '{provider_id}' is not configured for this deployment.")

    @staticmethod
    def _external_fallback(params: FlightInput, reason: str, **extra) -> ToolResult:
        return ToolResult(
            success=True,
            message=reason,
            data={
                "type": "flight_list",
                "items": [],
                "search_url": _flight_search_url(params),
                "live_inventory": False,
                "resolution_status": "provider_unavailable",
                **extra,
            },
            retry_safe=True,
        )

    def _search_duffel(self, params: FlightInput) -> ToolResult:
        """Search Duffel v2 flight offers. This endpoint does not book or collect payment."""
        try:
            parsed_date = datetime.strptime(params.date, "%Y-%m-%d").date()
            if parsed_date.isoformat() != params.date:
                raise ValueError("Date must use YYYY-MM-DD format.")
            if parsed_date < datetime.now().date():
                raise ValueError("The departure date is in the past.")
        except (TypeError, ValueError) as exc:
            return ToolResult(success=False, message=f"Flight search skipped: {exc}")

        try:
            origin_airports = resolve_airport_candidates(params.origin)
            destination_airports = resolve_airport_candidates(params.destination)
        except AirportResolutionError as exc:
            return self._external_fallback(
                params,
                "Airport resolution is temporarily unavailable. No live flight inventory was queried.",
                provider_error=str(exc),
            )

        if not origin_airports or not destination_airports:
            return self._external_fallback(
                params,
                "I couldn't resolve both locations to airports, so no live flight inventory was queried. Please specify a city or airport.",
                resolution_status="airport_not_found",
                origin_airport_candidates=origin_airports,
                destination_airport_candidates=destination_airports,
            )

        origin_iata = str(origin_airports[0].get("iata") or "").upper()
        destination_iata = str(destination_airports[0].get("iata") or "").upper()
        if not re.fullmatch(r"[A-Z]{3}", origin_iata) or not re.fullmatch(r"[A-Z]{3}", destination_iata):
            return self._external_fallback(params, "A valid airport code could not be resolved for both locations.", resolution_status="airport_not_found")

        slice_data = {
            "origin": origin_iata,
            "destination": destination_iata,
            "departure_date": params.date,
        }
        if params.departure_time_from or params.departure_time_to:
            time_window = {}
            if params.departure_time_from:
                time_window["from"] = params.departure_time_from
            if params.departure_time_to:
                time_window["to"] = params.departure_time_to
            slice_data["departure_time"] = time_window
        if params.arrival_time_from or params.arrival_time_to:
            arrival_window = {}
            if params.arrival_time_from:
                arrival_window["from"] = params.arrival_time_from
            if params.arrival_time_to:
                arrival_window["to"] = params.arrival_time_to
            slice_data["arrival_time"] = arrival_window

        request_data = {
            "slices": [slice_data],
            "passengers": [{"type": "adult"} for _ in range(params.passengers)],
        }
        if params.stops in {"nonstop", "1", "2"}:
            request_data["max_connections"] = {"nonstop": 0, "1": 1, "2": 2}[params.stops]
        if params.cabin_class:
            request_data["cabin_class"] = params.cabin_class

        try:
            with httpx.Client(timeout=httpx.Timeout(40.0)) as client:
                response = client.post(
                    "https://api.duffel.com/air/offer_requests",
                    params={"return_offers": "true", "supplier_timeout": "15000", "view": "offers"},
                    headers={
                        "Authorization": f"Bearer {settings.duffel_api_key.strip()}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Duffel-Version": "v2",
                    },
                    json={"data": request_data},
                )
                response.raise_for_status()
                payload = response.json()

            request_resource = payload.get("data") or {}
            offers = request_resource.get("offers") or []
            items = [
                item for offer in offers
                if isinstance(offer, dict)
                and (item := _duffel_offer_to_flight_item(offer)) is not None
            ]

            def departure_minutes(item: dict) -> int | None:
                try:
                    value = datetime.strptime(item["departure_time"], "%Y-%m-%d %H:%M")
                    return value.hour * 60 + value.minute
                except (KeyError, TypeError, ValueError):
                    return None

            earliest = (
                int(params.departure_time_from[:2]) * 60 + int(params.departure_time_from[3:])
                if params.departure_time_from else None
            )
            latest = (
                int(params.departure_time_to[:2]) * 60 + int(params.departure_time_to[3:])
                if params.departure_time_to else None
            )
            arrival_earliest = (
                int(params.arrival_time_from[:2]) * 60 + int(params.arrival_time_from[3:])
                if params.arrival_time_from else None
            )
            arrival_latest = (
                int(params.arrival_time_to[:2]) * 60 + int(params.arrival_time_to[3:])
                if params.arrival_time_to else None
            )

            def within_window(minutes, lower, upper):
                if lower is None and upper is None:
                    return True
                if minutes is None:
                    return False
                if lower is not None and upper is not None and lower > upper:
                    return minutes >= lower or minutes <= upper
                return not ((lower is not None and minutes < lower) or (upper is not None and minutes > upper))

            def arrival_minutes(item: dict) -> int | None:
                value = item.get("arrival_time")
                if not value:
                    return None
                try:
                    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
                    return parsed.hour * 60 + parsed.minute
                except ValueError:
                    return None

            filtered = []
            for item in items:
                minutes = departure_minutes(item)
                arr_minutes = arrival_minutes(item)
                if not within_window(minutes, earliest, latest):
                    continue
                if not within_window(arr_minutes, arrival_earliest, arrival_latest):
                    continue
                if params.stops == "nonstop" and item["stops"] != 0:
                    continue
                if params.stops in {"1", "2"} and item["stops"] > int(params.stops):
                    continue
                filtered.append(item)

            if params.sort_by == "departure_time":
                filtered.sort(key=lambda item: departure_minutes(item) if departure_minutes(item) is not None else 24 * 60)
            elif params.sort_by == "price":
                filtered.sort(key=lambda item: item["amount"] if item["amount"] is not None else float("inf"))

            filtered = filtered[:5]
            return ToolResult(
                success=True,
                message=(
                    f"Found {len(filtered)} live flight offer(s) from {origin_iata} to {destination_iata}."
                    if filtered else
                    f"Duffel returned no flight offers matching the requested route and filters ({origin_iata} to {destination_iata})."
                ),
                data={
                    "type": "flight_list",
                    "items": filtered,
                    "live_inventory": True,
                    "source": "Duffel",
                    "provider": "duffel",
                    "offer_request_id": request_resource.get("id"),
                    "result_count": len(filtered),
                    "filters_applied": {
                        **params.model_dump(exclude_none=True),
                        "origin_iata": origin_iata,
                        "destination_iata": destination_iata,
                    },
                    "origin_airport": origin_airports[0],
                    "destination_airport": destination_airports[0],
                    "origin_airport_candidates": origin_airports,
                    "destination_airport_candidates": destination_airports,
                },
                retry_safe=True,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            return self._external_fallback(
                params,
                f"Duffel flight search failed with HTTP {status_code}. No live flight results are available; verify the server-side provider configuration or check an external search.",
                provider_error=f"HTTP {status_code}",
            )
        except (httpx.RequestError, ValueError, TypeError, KeyError) as exc:
            return self._external_fallback(
                params,
                "Duffel flight search is temporarily unavailable. No live flight results are available; use an external search to check current schedules and fares.",
                provider_error=f"{type(exc).__name__}: {str(exc)[:300]}",
            )

    def _execute_trvl_cli(
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

        command = [
            "trvl",
            "flights",
            origin_iata,
            dest_iata,
            params.date,
            "--format",
            "json",
        ]
        if params.cabin_class:
            command.extend(["--cabin", params.cabin_class])
        # The CLI documents the "nonstop" filter. One/two-stop limits are
        # enforced against the returned segment count below.
        if params.stops == "nonstop":
            command.extend(["--stops", "nonstop"])

        try:
            result = subprocess.run(
                command,
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
                if not (
                    legs[0].get("departure_airport", {}).get("code", "") == origin_iata
                    and legs[-1].get("arrival_airport", {}).get("code", "") == dest_iata
                ):
                    continue
                stop_limit = {"nonstop": 0, "1": 1, "2": 2}.get(params.stops)
                if stop_limit is not None and len(legs) - 1 > stop_limit:
                    continue
                valid.append(flight)

            def departure_minutes(flight: dict) -> Optional[int]:
                legs = flight.get("legs") or []
                raw = (legs[0] or {}).get("departure_time") if legs else None
                if not isinstance(raw, str) or not raw.strip():
                    return None
                try:
                    parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                    return parsed.hour * 60 + parsed.minute
                except ValueError:
                    return None

            def clock_minutes(value: Optional[str]) -> Optional[int]:
                if value is None:
                    return None
                hour, minute = (int(part) for part in value.split(":"))
                return hour * 60 + minute

            earliest = clock_minutes(params.departure_time_from)
            latest = clock_minutes(params.departure_time_to)
            arrival_earliest = clock_minutes(params.arrival_time_from)
            arrival_latest = clock_minutes(params.arrival_time_to)

            def arrival_minutes(flight: dict) -> Optional[int]:
                legs = flight.get("legs") or []
                raw = (legs[-1] or {}).get("arrival_time") if legs else None
                if not isinstance(raw, str) or not raw.strip():
                    return None
                try:
                    parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                    return parsed.hour * 60 + parsed.minute
                except ValueError:
                    return None

            def within_window(minutes, lower, upper):
                if lower is None and upper is None:
                    return True
                if minutes is None:
                    return False
                if lower is not None and upper is not None and lower > upper:
                    return minutes >= lower or minutes <= upper
                return not ((lower is not None and minutes < lower) or (upper is not None and minutes > upper))

            time_filtered = []
            for flight in valid:
                dep_minutes = departure_minutes(flight)
                arr_minutes = arrival_minutes(flight)
                # Provider results without a verifiable requested time are excluded.
                if not within_window(dep_minutes, earliest, latest):
                    continue
                if not within_window(arr_minutes, arrival_earliest, arrival_latest):
                    continue
                time_filtered.append(flight)

            provider_route_matches = len(valid)
            valid = time_filtered
            matching_time_window = any(value is not None for value in (
                earliest, latest, arrival_earliest, arrival_latest
            ))

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
                        "resolution_status": (
                            "time_filter_no_results"
                            if provider_route_matches > 0 and matching_time_window
                            else "no_results"
                        ),
                        "filters_applied": params.model_dump(exclude_none=True),
                        "origin_airport": origin_airports[0],
                        "destination_airport": destination_airports[0],
                        "origin_airport_candidates": origin_airports,
                        "destination_airport_candidates": destination_airports,
                    },
                )

            # Price ranking is only meaningful when all offers use one currency.
            currencies = {
                str(flight.get("currency") or "").upper().strip()
                for flight in valid
            }
            if params.sort_by == "departure_time":
                valid.sort(key=lambda item: departure_minutes(item) if departure_minutes(item) is not None else 24 * 60)
            elif params.sort_by == "price" and len(currencies) == 1 and "" not in currencies:
                valid.sort(
                    key=lambda item: (
                        float(item.get("price"))
                        if str(item.get("price") or "").replace(".", "", 1).isdigit()
                        else float("inf")
                    )
                )

            structured = []

            for flight in valid[:5]:
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
                        "departure_time": segments[0]["departure"] if segments else None,
                        "arrival_time": segments[-1]["arrival"] if segments else None,
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
                    "filters_applied": params.model_dump(exclude_none=True),
                    "result_count": len(valid),
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
    city: str = Field(..., min_length=3, max_length=200)
    check_in: str = Field(...)
    check_out: str = Field(...)
    travellers: int = Field(default=2, ge=1, le=20)
    budget: Optional[float] = Field(default=None, ge=0)
    rooms: int = Field(default=1, ge=1, le=9)
    country_code: str = Field(
        default="in",
        pattern=r"^[a-z]{2}$",
        description="ISO-3166 alpha-2 destination country for Booking.com destination resolution. Use 'in' for Indian cities.",
    )
    booker_country: str = Field(
        default="in",
        pattern=r"^[a-z]{2}$",
        description="ISO-3166 alpha-2 country of the traveller making the search.",
    )
    booker_currency: str = Field(
        default="INR",
        pattern=r"^[A-Z]{3}$",
        description="ISO-4217 currency requested for displayed prices. Use the user's saved default currency when present.",
    )

    @field_validator("country_code", "booker_country", mode="before")
    @classmethod
    def normalize_country_codes(cls, value):
        normalized = str(value or "").strip().lower()
        if not re.fullmatch(r"[a-z]{2}", normalized):
            raise ValueError("Country codes must be ISO-3166 alpha-2.")
        return normalized

    @field_validator("booker_currency", mode="before")
    @classmethod
    def normalize_booker_currency(cls, value):
        normalized = str(value or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("Currency must be an ISO-4217 alpha-3 code.")
        return normalized


class RefreshFlightOfferInput(BaseModel):
    offer_id: str = Field(..., min_length=8, max_length=80, pattern=r"^off_[A-Za-z0-9]+$")


class RefreshFlightOfferTool(BaseTool):
    name = "refresh_flight_offer"
    description = (
        "Retrieve the latest state and price of a previously returned Duffel flight offer. "
        "This only refreshes an offer; it does not create a booking or collect payment."
    )
    capability = "travel"
    input_schema = RefreshFlightOfferInput
    requires_confirmation = False
    is_mutating = False
    supported_operations = ("retrieve",)

    def __init__(self):
        self.provider_adapters = ({"provider_id": "duffel", "display_name": "Duffel"},)
        if not settings.duffel_api_key.strip():
            self.execution_status = "requires_auth"
            self.requires_auth = True

    def execute(self, ctx: ToolContext, params: RefreshFlightOfferInput) -> ToolResult:
        if not settings.duffel_api_key.strip():
            return ToolResult(success=False, message="Flight offer refresh requires a Duffel API token configured on the server.")
        try:
            with httpx.Client(timeout=httpx.Timeout(25.0)) as client:
                response = client.get(
                    f"https://api.duffel.com/air/offers/{params.offer_id}",
                    headers={
                        "Authorization": f"Bearer {settings.duffel_api_key.strip()}",
                        "Accept": "application/json",
                        "Duffel-Version": "v2",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            item = _duffel_offer_to_flight_item(payload.get("data") or {})
            if not item:
                return ToolResult(success=False, message="Duffel returned an offer without usable flight segments.")
            item["refreshed_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            return ToolResult(
                success=True,
                message=f"Latest flight offer retrieved. Current displayed total: {item['price']}. No booking has been made.",
                data={
                    "type": "flight_list",
                    "items": [item],
                    "live_inventory": True,
                    "source": "Duffel",
                    "provider": "duffel",
                    "refreshed": True,
                    "result_count": 1,
                },
                retry_safe=True,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return ToolResult(success=False, message="This flight offer is no longer available. Search again for current options.")
            return ToolResult(success=False, message=f"Duffel could not refresh this offer (HTTP {exc.response.status_code}).", retry_safe=True)
        except httpx.RequestError:
            return ToolResult(success=False, message="Duffel could not be reached to refresh the offer. Please retry.", retry_safe=True)


class StayApiHotelTool(BaseTool):
    name = "search_hotels_stayapi"

    description = (
        "Search live hotel offers through configured Booking.com Demand API v3.3 "
        "or the legacy TRVL CLI adapter. Returns options and redirect links only; "
        "does not create a reservation or process payment. Budget is MAXIMUM TOTAL "
        "price for the entire stay."
    )

    input_schema = HotelInput
    requires_confirmation = False
    capability = "travel"
    provider_adapters = ()
    supported_operations = ("search",)

    def __init__(self):
        booking_mode = settings.booking_mode.strip().lower()
        booking_configured = bool(
            settings.booking_api_token.strip()
            and settings.booking_affiliate_id.strip()
        )
        if booking_mode == "search_and_redirect":
            self.provider_adapters = ({
                "provider_id": "booking_demand",
                "display_name": "Booking.com Demand API",
            },)
            if not booking_configured:
                self.execution_status = "requires_auth"
                self.requires_auth = True
        else:
            self.provider_adapters = ({
                "provider_id": "trvl_cli",
                "display_name": "TRVL CLI adapter",
            },)

    def execute(self, ctx: ToolContext, params: HotelInput) -> ToolResult:
        if settings.booking_mode.strip().lower() == "search_and_redirect":
            return self._search_booking_demand(params)
        return self._execute_trvl_cli(ctx, params)

    def execute_for_provider(
        self, ctx: ToolContext, params: HotelInput, provider_id: str
    ) -> ToolResult:
        provider_id = str(provider_id).strip().lower()
        if provider_id == "booking_demand":
            return self._search_booking_demand(params)
        if provider_id == "trvl_cli":
            return self._execute_trvl_cli(ctx, params)
        return ToolResult(success=False, message=f"Hotel provider '{provider_id}' is not configured.")

    @staticmethod
    def _booking_headers() -> dict:
        return {
            "Authorization": f"Bearer {settings.booking_api_token.strip()}",
            "X-Affiliate-Id": settings.booking_affiliate_id.strip(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _booking_text(value) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return str(
                value.get("en-gb")
                or value.get("en")
                or next(iter(value.values()), "")
            ).strip()
        return ""

    def _search_booking_demand(self, params: HotelInput) -> ToolResult:
        """Search Booking.com Demand API v3.3; redirect to Booking.com to book."""
        if not settings.booking_api_token.strip() or not settings.booking_affiliate_id.strip():
            return ToolResult(
                success=False,
                message="Booking.com Demand API requires a server-side API token and affiliate ID. Connect approved partner credentials or use the standard hotel search handoff.",
            )

        try:
            check_in = datetime.strptime(params.check_in, "%Y-%m-%d").date()
            check_out = datetime.strptime(params.check_out, "%Y-%m-%d").date()
            if check_in.isoformat() != params.check_in or check_out.isoformat() != params.check_out:
                raise ValueError("Dates must use YYYY-MM-DD format.")
            if check_out <= check_in:
                raise ValueError("Check-out must be after check-in.")
            if check_in < datetime.now().date():
                raise ValueError("Check-in date is in the past.")
        except (TypeError, ValueError) as exc:
            return ToolResult(success=False, message=f"Hotel search skipped: {exc}")

        base_url = (
            settings.booking_api_base_url.strip()
            or "https://demandapi.booking.com/3.3"
        ).rstrip("/")
        base_host = (urlparse(base_url).hostname or "").lower()
        if (
            urlparse(base_url).scheme != "https"
            or base_host not in {
                "demandapi.booking.com",
                "demandapi-sandbox.booking.com",
            }
        ):
            return ToolResult(
                success=False,
                message="Booking.com API base URL must use the official HTTPS Demand API host.",
            )

        headers = self._booking_headers()
        try:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                location_response = client.post(
                    f"{base_url}/common/autocomplete",
                    headers=headers,
                    json={
                        "query": params.city.strip(),
                        "language": "en-gb",
                        "country": params.country_code,
                        "filters": {"types": ["city"]},
                    },
                )
                location_response.raise_for_status()
                location_payload = location_response.json()

                suggestions = location_payload.get("data") or []
                city_candidates = [
                    item for item in suggestions
                    if isinstance(item, dict)
                    and str(item.get("type") or "").lower() == "city"
                    and str((item.get("location") or {}).get("country") or "").lower()
                        == params.country_code.lower()
                ]
                requested_city = " ".join(params.city.casefold().split())
                exact_matches = [
                    item for item in city_candidates
                    if self._booking_text(item.get("name")).casefold() == requested_city
                    or self._booking_text((item.get("location") or {}).get("city_name")).casefold() == requested_city
                ]
                selected_city = exact_matches[0] if exact_matches else (
                    city_candidates[0] if len(city_candidates) == 1 else None
                )
                if selected_city is None:
                    return ToolResult(
                        success=False,
                        message=(
                            f"Booking.com could not resolve '{params.city}' unambiguously in "
                            f"{params.country_code.upper()}. Add the country or a more specific destination."
                        ),
                        data={
                            "type": "hotel_list",
                            "items": [],
                            "live_inventory": False,
                            "resolution_status": "ambiguous_destination",
                            "destination_suggestions": [
                                self._booking_text(item.get("name"))
                                for item in city_candidates[:5]
                            ],
                        },
                    )

                location = selected_city.get("location") or {}
                city_id = location.get("city") or selected_city.get("id")
                try:
                    city_id = int(city_id)
                except (TypeError, ValueError):
                    return ToolResult(
                        success=False,
                        message="Booking.com returned an invalid city identifier. Please refine the destination.",
                    )

                search_request = {
                    "booker": {
                        "country": params.booker_country,
                        "platform": "desktop",
                    },
                    "currency": params.booker_currency,
                    "checkin": params.check_in,
                    "checkout": params.check_out,
                    "city": city_id,
                    "extras": ["products"],
                    "guests": {
                        "number_of_adults": params.travellers,
                        "number_of_rooms": params.rooms,
                    },
                    "rows": 10,
                    "sort": {"by": "price", "direction": "ascending"},
                }
                search_response = client.post(
                    f"{base_url}/accommodations/search",
                    headers=headers,
                    json=search_request,
                )
                search_response.raise_for_status()
                search_payload = search_response.json()

                raw_results = search_payload.get("data") or []
                property_ids = [
                    item.get("id")
                    for item in raw_results[:10]
                    if isinstance(item, dict) and item.get("id") is not None
                ]
                detail_map = {}
                if property_ids:
                    details_response = client.post(
                        f"{base_url}/accommodations/details",
                        headers=headers,
                        json={
                            "accommodations": property_ids,
                            "extras": ["photos"],
                            "languages": ["en-gb"],
                        },
                    )
                    details_response.raise_for_status()
                    details_payload = details_response.json()
                    detail_map = {
                        str(item.get("id")): item
                        for item in (details_payload.get("data") or [])
                        if isinstance(item, dict) and item.get("id") is not None
                    }
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            return ToolResult(
                success=False,
                message=(
                    f"Booking.com hotel search failed with HTTP {status_code}. "
                    "Check Demand API partner permissions and server credentials."
                ),
                data={
                    "type": "hotel_list",
                    "items": [],
                    "live_inventory": False,
                    "provider": "booking_demand",
                    "resolution_status": "provider_error",
                },
                retry_safe=status_code >= 500 or status_code in {408, 429},
            )
        except (httpx.RequestError, ValueError, TypeError) as exc:
            return ToolResult(
                success=False,
                message=f"Booking.com hotel search is temporarily unavailable ({type(exc).__name__}).",
                data={
                    "type": "hotel_list",
                    "items": [],
                    "live_inventory": False,
                    "provider": "booking_demand",
                    "resolution_status": "provider_unavailable",
                },
                retry_safe=True,
            )

        nights = (check_out - check_in).days
        candidates = []
        excluded = 0
        for result in raw_results:
            if not isinstance(result, dict):
                continue
            detail = detail_map.get(str(result.get("id")), {})
            name = self._booking_text(
                result.get("name") or detail.get("name")
            )
            if not name:
                continue

            price_data = result.get("price") or {}
            display_price = price_data.get("display") or {}
            total_price = price_data.get("total") or {}
            currency_data = result.get("currency") or {}
            booker_amount = (
                display_price.get("booker_currency")
                if display_price.get("booker_currency") is not None
                else total_price.get("booker_currency")
            )
            if booker_amount is not None:
                raw_amount = booker_amount
                currency = str(currency_data.get("booker") or "").upper().strip()
            else:
                raw_amount = total_price.get("accommodation_currency")
                currency = str(currency_data.get("accommodation") or "").upper().strip()
            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                continue
            # Never infer a currency from a country code or silently relabel a price.
            if amount <= 0 or not re.fullmatch(r"[A-Z]{3}", currency):
                continue

            if params.budget is not None and currency == "INR" and amount > params.budget:
                excluded += 1
                continue

            detail_location = detail.get("location") or result.get("location") or {}
            address = detail_location.get("address") or detail_location.get("address_line") or ""
            if isinstance(address, dict):
                address = address.get("full") or address.get("text") or ""

            photos = detail.get("photos") or result.get("photos") or []
            image_url = ""
            if photos and isinstance(photos[0], dict):
                image_url = photos[0].get("url") or photos[0].get("large_url") or ""

            rating_data = detail.get("rating") or result.get("rating") or {}
            rating = (
                rating_data.get("review_score")
                if isinstance(rating_data, dict)
                else rating_data
            )

            booking_url = result.get("url") or detail.get("url")
            parsed_booking_url = urlparse(booking_url) if isinstance(booking_url, str) else None
            if not (
                parsed_booking_url
                and parsed_booking_url.scheme == "https"
                and (
                    parsed_booking_url.hostname == "booking.com"
                    or (parsed_booking_url.hostname or "").endswith(".booking.com")
                )
            ):
                booking_url = ""

            candidates.append({
                "name": name,
                "address": str(address),
                "price_per_night": format_price(amount / nights, currency),
                "total_stay": format_price(amount, currency),
                "currency": currency,
                "nights": nights,
                "total_inr": amount if currency == "INR" else None,
                "booking_url": booking_url,
                "image_url": image_url,
                "rating": rating or "",
                "provider": "Booking.com Demand API",
                "accommodation_id": result.get("id"),
            })

        candidates.sort(
            key=lambda item: item["total_inr"] if item["total_inr"] is not None else float("inf")
        )
        items = candidates[:5]
        fallback_url = _hotel_search_url(params)
        return ToolResult(
            success=True,
            message=(
                f"Found {len(items)} live Booking.com accommodation option(s) in {params.city}."
                if items
                else (
                    f"No Booking.com accommodation options matched {params.city} for those dates."
                    + (f" {excluded} result(s) exceeded your ₹{params.budget:,.0f} total budget." if excluded else "")
                )
            ),
            data={
                "type": "hotel_list",
                "items": items,
                "search_url": (
                    fallback_url
                    if not items or any(not item.get("booking_url") for item in items)
                    else None
                ),
                "live_inventory": True,
                "source": "Booking.com Demand API v3.3",
                "provider": "booking_demand",
                "request_id": search_payload.get("request_id"),
                "search_context": {
                    "city": params.city,
                    "city_id": city_id,
                    "check_in": params.check_in,
                    "check_out": params.check_out,
                    "travellers": params.travellers,
                    "rooms": params.rooms,
                    "budget": params.budget,
                    "currency": params.booker_currency,
                },
                "budget_filter_applied": params.budget is not None and all(
                    item["currency"] == "INR" for item in items
                ),
                "excluded_over_budget": excluded,
            },
            retry_safe=True,
        )

    def _execute_trvl_cli(
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
