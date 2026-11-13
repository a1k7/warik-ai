"""Swiggy Food discovery service with an explicitly labelled local demo mode."""

from typing import Any

from app.core.config import settings
from app.integrations.swiggy.client import SwiggyMCPClient, SwiggyMCPError


DEMO_ADDRESSES = [
    {
        "id": "warik-demo-address",
        "addressCategory": "Demo",
        "addressLine": "Demo delivery address — not a real delivery location",
    }
]

DEMO_RESTAURANTS = [
    {
        "id": "demo-restaurant-1",
        "name": "The Biryani Kitchen",
        "cuisines": ["Biryani", "North Indian"],
        "avgRating": 4.3,
        "distanceKm": 2.4,
        "deliveryTimeMinutes": 35,
        "availabilityStatus": "OPEN",
    },
    {
        "id": "demo-restaurant-2",
        "name": "Spice Route Kitchen",
        "cuisines": ["North Indian", "Mughlai"],
        "avgRating": 4.2,
        "distanceKm": 3.1,
        "deliveryTimeMinutes": 40,
        "availabilityStatus": "OPEN",
    },
    {
        "id": "demo-restaurant-3",
        "name": "South Bowl House",
        "cuisines": ["South Indian"],
        "avgRating": 4.4,
        "distanceKm": 1.8,
        "deliveryTimeMinutes": 30,
        "availabilityStatus": "CLOSED",
    },
]


def _require_mock_or_live_token(access_token: str | None) -> str:
    mode = settings.swiggy_mode.strip().lower()
    if mode == "mock":
        return mode
    if mode != "production":
        raise SwiggyMCPError(
            f"Swiggy mode '{mode}' is not enabled for restaurant discovery."
        )
    if not access_token:
        raise SwiggyMCPError(
            "Your Swiggy account is not connected. Complete OAuth authorization first."
        )
    return mode


def _client(access_token: str) -> SwiggyMCPClient:
    return SwiggyMCPClient(
        endpoint=settings.swiggy_food_mcp_url,
        access_token=access_token,
        timeout_seconds=20.0,
    )


async def get_addresses(
    access_token: str | None = None,
) -> dict[str, Any]:
    mode = _require_mock_or_live_token(access_token)

    if mode == "mock":
        return {
            "mode": "mock",
            "is_mock": True,
            "addresses": DEMO_ADDRESSES,
        }

    data = await _client(access_token).call_tool("get_addresses", {})
    addresses = data.get("addresses", [])
    if not isinstance(addresses, list):
        raise SwiggyMCPError("Swiggy returned an invalid addresses list.")
    return {
        "mode": "live",
        "is_mock": False,
        "addresses": addresses,
    }


async def search_restaurants(
    query: str,
    address_id: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    mode = _require_mock_or_live_token(access_token)
    clean_query = query.strip()
    clean_address = address_id.strip()

    if not clean_query:
        raise ValueError("Search query cannot be empty.")
    if not clean_address:
        raise ValueError("A delivery address is required.")

    if mode == "mock":
        restaurants = [
            item.copy()
            for item in DEMO_RESTAURANTS
            if item["availabilityStatus"] == "OPEN"
        ]
        return {
            "mode": "mock",
            "is_mock": True,
            "query": clean_query,
            "address_id": clean_address,
            "restaurants": restaurants,
            "count": len(restaurants),
            "has_more": False,
            "next_offset": None,
            "notice": "Demo results only. These are not live Swiggy restaurants or offers.",
        }

    data = await _client(access_token).call_tool(
        "search_restaurants",
        {
            "addressId": clean_address,
            "query": clean_query,
        },
    )
    restaurants = data.get("restaurants", [])
    if not isinstance(restaurants, list):
        raise SwiggyMCPError("Swiggy returned an invalid restaurants list.")

    open_restaurants = [
        item
        for item in restaurants
        if isinstance(item, dict)
        and str(item.get("availabilityStatus", "")).upper() == "OPEN"
    ]

    return {
        "mode": "live",
        "is_mock": False,
        "query": clean_query,
        "address_id": clean_address,
        "restaurants": open_restaurants,
        "count": len(open_restaurants),
        "has_more": bool(data.get("hasMore", False)),
        "next_offset": data.get("nextOffset"),
    }
