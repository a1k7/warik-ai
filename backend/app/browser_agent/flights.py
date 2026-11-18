"""Server-side SerpApi Google Flights integration.

The API key is read only from backend settings and is never returned to the client.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import httpx

from app.core.config import settings

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
CITY_CODES = {
    "bengaluru": "BLR", "bangalore": "BLR",
    "goa": "GOI,GOX", "panaji": "GOI", "mopa": "GOX",
    "delhi": "DEL", "new delhi": "DEL",
    "mumbai": "BOM", "bombay": "BOM",
    "hyderabad": "HYD", "chennai": "MAA", "madras": "MAA",
    "kolkata": "CCU", "calcutta": "CCU",
    "pune": "PNQ", "ahmedabad": "AMD", "jaipur": "JAI",
    "kochi": "COK", "cochin": "COK", "lucknow": "LKO",
    "varanasi": "VNS", "chandigarh": "IXC", "bhopal": "BHO",
}
TIME_RANGES = {
    "morning": "5,12",
    "afternoon": "12,17",
    "evening": "17,23",
    "night": "19,23",
}


def airport_ids(city: str) -> str:
    value = city.strip()
    if len(value) == 3 and value.isalpha():
        return value.upper()
    code = CITY_CODES.get(value.casefold())
    if not code:
        raise ValueError(
            f"I don't have an airport mapping for '{city}'. Use a major city name or a 3-letter IATA code."
        )
    return code


def requested_date(goal: str, today: date | None = None) -> date:
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    lowered = goal.casefold()
    if "day after tomorrow" in lowered:
        return today + timedelta(days=2)
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    if "today" in lowered or "tonight" in lowered:
        return today
    import re
    match = re.search(r"\\b(20\\d{2}-\\d{2}-\\d{2})\\b", goal)
    if match:
        parsed = date.fromisoformat(match.group(1))
        if parsed < today:
            raise ValueError("The requested departure date is in the past.")
        return parsed
    raise ValueError("Please specify a departure date, such as tomorrow or 2026-11-19.")


def requested_time_range(goal: str) -> str | None:
    lowered = goal.casefold()
    for label, value in TIME_RANGES.items():
        if label in lowered:
            return value
    return None


def _normalise_flight(item: dict) -> dict | None:
    segments = item.get("flights") or []
    # Stops must be verified from the actual returned segments, not inferred from text.
    if len(segments) != 1 or item.get("layovers"):
        return None
    segment = segments[0]
    departure = segment.get("departure_airport") or {}
    arrival = segment.get("arrival_airport") or {}
    price = item.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    return {
        "airline": segment.get("airline") or "Airline not supplied",
        "flight_number": segment.get("flight_number") or "Not supplied",
        "departure": departure.get("time"),
        "arrival": arrival.get("time"),
        "origin_airport": departure.get("id"),
        "destination_airport": arrival.get("id"),
        "duration_minutes": segment.get("duration") or item.get("total_duration"),
        "price": int(price),
        "currency": "INR",
        "stops": 0,
        "source": "Google Flights via SerpApi",
    }


async def search_live_flights(
    origin: str,
    destination: str,
    goal: str,
) -> dict:
    """Fetch current flight search results; never substitute demo inventory."""
    api_key = settings.serpapi_api_key.strip()
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY is missing. Add it to backend/.env and restart the backend.")

    departure_id = airport_ids(origin)
    arrival_id = airport_ids(destination)
    travel_date = requested_date(goal)
    params = {
        "engine": "google_flights",
        "api_key": api_key,
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": travel_date.isoformat(),
        "type": "2",
        "stops": "1",
        "sort_by": "2",
        "currency": "INR",
        "gl": "in",
        "hl": "en",
        "adults": "1",
        "travel_class": "1",
    }
    time_range = requested_time_range(goal)
    if time_range:
        params["outbound_times"] = time_range

    timeout = httpx.Timeout(settings.serpapi_timeout_seconds, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(SERPAPI_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()

    metadata = payload.get("search_metadata") or {}
    if metadata.get("status") != "Success":
        raise RuntimeError(payload.get("error") or f"SerpApi search status: {metadata.get('status', 'unknown')}")

    candidates = (payload.get("best_flights") or []) + (payload.get("other_flights") or [])
    flights = []
    seen = set()
    for candidate in candidates:
        flight = _normalise_flight(candidate)
        if not flight:
            continue
        identity = (flight["flight_number"], flight["departure"], flight["price"])
        if identity in seen:
            continue
        seen.add(identity)
        flights.append(flight)

    flights.sort(key=lambda item: (item["price"], item["departure"] or ""))
    search_url = metadata.get("google_flights_url")
    parsed = urlparse(search_url or "")
    if parsed.scheme != "https" or parsed.hostname not in {"google.com", "www.google.com"}:
        search_url = None

    return {
        "source": "Google Flights via SerpApi",
        "searched_at": metadata.get("created_at") or datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "departure_date": travel_date.isoformat(),
        "origin": origin,
        "destination": destination,
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "time_range": time_range,
        "currency": "INR",
        "options": flights,
        "search_url": search_url,
        "search_id": metadata.get("id"),
        "is_live_provider_data": True,
    }


def render_live_results_html(result: dict) -> str:
    """Render only API-returned results into the local browser page."""
    rows = []
    for index, flight in enumerate(result["options"]):
        airline = escape(str(flight["airline"]))
        number = escape(str(flight["flight_number"]))
        departure = escape(str(flight["departure"] or "Time unavailable"))
        arrival = escape(str(flight["arrival"] or "Time unavailable"))
        price = f"₹{flight['price']:,}"
        rows.append(
            f'<article class="flight-card" data-flight-card data-flight-id="live-{index}" '
            f'data-price="{flight["price"]}"><div><strong>{airline} · {number}</strong>'
            f'<div>{escape(result["origin"])} → {escape(result["destination"])}</div></div>'
            f'<div><strong>{departure} → {arrival}</strong><div>Non-stop · '
            f'{flight["duration_minutes"] or "Duration unavailable"} min</div></div>'
            f'<div><strong>{price}</strong><div>Live search result · INR</div></div></article>'
        )
    if not rows:
        body = "<p>No verified non-stop flights matched these filters. No sample results have been substituted.</p>"
    else:
        body = "".join(rows)
    source_link = (
        f'<p><a href="{escape(result["search_url"], quote=True)}" target="_blank" rel="noreferrer">'
        "Open this search on Google Flights</a></p>" if result.get("search_url") else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Warik · Live flight results</title>"
        "<style>body{font:16px system-ui;background:#f4f6fa;color:#14213a;padding:32px}"
        ".flight-card{display:grid;grid-template-columns:1fr 1fr .5fr;gap:18px;padding:20px;"
        "margin:12px 0;background:white;border:1px solid #dbe1eb;border-radius:14px}"
        ".source{color:#177346;font-weight:700}a{color:#315bd6}</style></head><body>"
        "<h1>Live flight search results</h1><p class='source'>LIVE PROVIDER DATA · GOOGLE FLIGHTS VIA SERPAPI</p>"
        f"<p>{escape(result['origin'])} → {escape(result['destination'])} · "
        f"{escape(result['departure_date'])} · Non-stop only · INR</p>"
        f"<section id='results'>{body}</section>{source_link}</body></html>"
    )
