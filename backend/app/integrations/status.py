"""Truthful provider availability reporting.

Configuration does not imply provider approval, connectivity or live inventory.
"""

from app.core.config import settings


def _configured(value: str) -> bool:
    return bool(value and value.strip())


def get_provider_status() -> list[dict]:
    swiggy_mode = settings.swiggy_mode.strip().lower()
    agoda_mode = settings.agoda_mode.strip().lower()
    booking_mode = settings.booking_mode.strip().lower()

    swiggy_states = {
        "mock": ("development", False, "Local mock data only"),
        "development": ("development", False, "Development access; live access not verified"),
        "staging": ("staging", False, "Staging access; production access not verified"),
        "production": ("pending_verification", False, "Production credentials and approval must be verified"),
        "disabled": ("unavailable", False, "Integration disabled"),
    }

    swiggy_state, swiggy_transactions, swiggy_message = swiggy_states.get(
        swiggy_mode,
        ("invalid_configuration", False, "Unknown SWIGGY_MODE"),
    )

    agoda_ready = (
        agoda_mode == "production"
        and _configured(settings.agoda_affiliate_url)
        and _configured(settings.agoda_affiliate_id)
    )
    if agoda_mode == "redirect_only":
        agoda_state = "redirect_only"
        agoda_message = (
            "Affiliate handoff is not configured"
            if not _configured(settings.agoda_affiliate_url)
            else "Affiliate handoff configured; live inventory is not available through this adapter"
        )
    elif agoda_mode in {"sandbox", "production"}:
        agoda_state = "configured_pending_verification" if agoda_ready else "unavailable"
        agoda_message = "Partner API access must be verified before use"
    else:
        agoda_state = "unavailable"
        agoda_message = "Agoda integration disabled or misconfigured"

    booking_ready = (
        booking_mode in {"sandbox", "production"}
        and _configured(settings.booking_api_base_url)
        and _configured(settings.booking_api_token)
        and _configured(settings.booking_affiliate_id)
    )

    if booking_mode == "disabled":
        booking_state = "unavailable"
        booking_message = "Booking.com integration disabled"
    elif booking_mode in {"sandbox", "production"}:
        booking_state = "configured_pending_verification" if booking_ready else "unavailable"
        booking_message = (
            "Credentials configured; connectivity and partner permissions not yet verified"
            if booking_ready
            else "Required partner configuration is missing"
        )
    else:
        booking_state = "invalid_configuration"
        booking_message = "Unknown BOOKING_MODE"

    return [
        {
            "provider_id": "swiggy",
            "display_name": "Swiggy MCP",
            "mode": swiggy_mode,
            "state": swiggy_state,
            "live_inventory_verified": False,
            "transactions_enabled": swiggy_transactions,
            "message": swiggy_message,
            "services": ["food", "instamart", "dineout", "scenes"],
        },
        {
            "provider_id": "agoda",
            "display_name": "Agoda",
            "mode": agoda_mode,
            "state": agoda_state,
            "live_inventory_verified": False,
            "transactions_enabled": False,
            "message": agoda_message,
            "affiliate_handoff_configured": _configured(settings.agoda_affiliate_url),
        },
        {
            "provider_id": "booking",
            "display_name": "Booking.com",
            "mode": booking_mode,
            "state": booking_state,
            "live_inventory_verified": False,
            "transactions_enabled": False,
            "message": booking_message,
        },
    ]
