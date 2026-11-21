"""Direct StayAPI Booking.com destination and hotel-search adapter."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

BASE_URL = "https://api.stayapi.com/v1"


class StayAPIError(RuntimeError):
    """Safe, credential-free provider error."""


class StayAPIClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 25.0,
        base_url: str = BASE_URL,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise StayAPIError("StayAPI key is not configured.")
        self._api_key = clean_key
        self._timeout = max(3.0, min(float(timeout_seconds), 60.0))
        self._base_url = base_url.rstrip("/")

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"x-api-key": self._api_key, "Accept": "application/json"},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise StayAPIError("StayAPI request timed out.") from exc
        except httpx.HTTPError as exc:
            raise StayAPIError("StayAPI could not be reached.") from exc

        if response.status_code >= 400:
            # Do not echo provider response bodies; they may contain sensitive data.
            raise StayAPIError(f"StayAPI returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise StayAPIError("StayAPI returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise StayAPIError("StayAPI returned an unexpected response shape.")
        if payload.get("success") is False:
            raise StayAPIError("StayAPI could not complete the hotel request.")
        return payload

    def search_hotels(
        self,
        *,
        city: str,
        check_in: str,
        check_out: str,
        adults: int = 2,
        rooms: int = 1,
        currency: str = "INR",
        language: str = "en-in",
        market: str = "IN",
        limit: int = 25,
    ) -> dict[str, Any]:
        city = str(city or "").strip()
        if not city:
            raise ValueError("Hotel destination cannot be empty.")
        try:
            start = datetime.strptime(check_in, "%Y-%m-%d").date()
            end = datetime.strptime(check_out, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise ValueError("Hotel dates must use YYYY-MM-DD.") from exc
        if end <= start:
            raise ValueError("Check-out must be after check-in.")
        if not 1 <= int(adults) <= 20 or not 1 <= int(rooms) <= 10:
            raise ValueError("Hotel guest or room count is outside supported limits.")

        destination = self._get(
            "/booking/destinations/lookup",
            {"query": city, "language": language},
        )
        dest_id = destination.get("dest_id")
        if dest_id is None or str(dest_id).strip() == "":
            raise StayAPIError("StayAPI could not resolve that hotel destination.")
        dest_type = str(destination.get("dest_type") or "CITY").upper()

        search = self._get(
            "/booking/search",
            {
                "dest_id": str(dest_id),
                "dest_type": dest_type,
                "checkin": start.isoformat(),
                "checkout": end.isoformat(),
                "adults": int(adults),
                "rooms": int(rooms),
                "rows_per_page": max(1, min(int(limit), 100)),
                "offset": 0,
                "language": language,
                "currency": currency.upper(),
                "market": market.upper(),
            },
        )
        rows = search.get("data", [])
        if not isinstance(rows, list):
            raise StayAPIError("StayAPI returned an invalid hotel list.")

        nights = (end - start).days
        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("hotel_name") or row.get("name") or "").strip()
            if not name:
                continue
            try:
                total = float(row.get("min_total_price"))
            except (TypeError, ValueError):
                total = None
            code = str(row.get("currency_code") or currency).upper()
            hotel_url = row.get("url")
            if not isinstance(hotel_url, str) or not hotel_url.startswith("https://"):
                hotel_url = ""
            items.append(
                {
                    "name": name,
                    "hotel_id": row.get("hotel_id"),
                    "address": row.get("address") or "",
                    "price_per_night": (
                        f"{code} {total / nights:,.2f}" if total is not None else "Price unavailable"
                    ),
                    "price_per_night_amount": (total / nights if total is not None else None),
                    "total_stay_amount": total,
                    "price_per_night_display": (
                        f"{code} {total / nights:,.2f}" if total is not None else "Price unavailable"
                    ),
                    "total_stay": (f"{code} {total:,.2f}" if total is not None else "Price unavailable"),
                    "currency": code,
                    "total_inr": total if code == "INR" else None,
                    "nights": nights,
                    "booking_url": hotel_url,
                    "image_url": row.get("image_url") or "",
                    "rating": row.get("review_score") or row.get("star_rating") or "",
                    "review_count": row.get("review_count"),
                    "star_rating": row.get("star_rating"),
                    "is_free_cancellable": bool(row.get("is_free_cancellable")),
                    "is_no_prepayment": bool(row.get("is_no_prepayment_block")),
                    "check_in": row.get("checkin") or start.isoformat(),
                    "check_out": row.get("checkout") or end.isoformat(),
                    "price_basis": "provider_min_total_price",
                }
            )

        return {
            "items": items,
            "provider": "stayapi_booking",
            "live_inventory": True,
            "retrieved_at": search.get("retrieved_at"),
            "destination": {
                "id": str(dest_id),
                "type": dest_type,
                "label": destination.get("normalized_query") or city,
                "suggestions": destination.get("suggestions") or [],
            },
            "pagination": search.get("pagination") or {},
            "effective_market": search.get("effective_market") or {},
        }
