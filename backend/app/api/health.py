import logging
import shutil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.database.session import get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "service": "warik-ai-backend",
            "database": "ok",
        }
    except SQLAlchemyError:
        logger.exception("Health check database query failed")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "service": "warik-ai-backend",
                "database": "unavailable",
            },
        )


def build_capability_status(
    config: Any = settings,
    *,
    cli_available: bool | None = None,
) -> dict[str, Any]:
    """Return safe configuration readiness without exposing credentials.

    This is a configuration snapshot, not a live provider health check.
    Actual availability and offer validity are checked when a tool runs.
    """
    if cli_available is None:
        cli_available = shutil.which("trvl") is not None

    services: list[dict[str, str]] = []

    llm_provider = str(getattr(config, "llm_provider", "ollama")).strip().lower()
    if llm_provider == "groq":
        llm_ready = bool(str(getattr(config, "groq_api_key", "")).strip())
        services.append({
            "id": "assistant",
            "label": "AI reasoning",
            "status": "configured" if llm_ready else "missing_credentials",
            "detail": "Groq is selected. Requests still depend on provider availability."
            if llm_ready else "Groq is selected, but GROQ_API_KEY is not configured.",
        })
    else:
        services.append({
            "id": "assistant",
            "label": "AI reasoning",
            "status": "local_configured",
            "detail": (
                f"Local Ollama model: {getattr(config, 'ollama_model', 'configured')}. "
                "The local model server must be running."
            ),
        })

    if str(getattr(config, "duffel_api_key", "")).strip():
        flight_status = "configured"
        flight_detail = "Duffel flight-offer search and offer refresh are configured. Ticketing and payment are not enabled."
    elif cli_available:
        flight_status = "legacy_provider"
        flight_detail = "TRVL CLI is available. Live results depend on its provider setup."
    else:
        flight_status = "external_search_only"
        flight_detail = "No live flight provider is configured. Warik can provide an external search handoff."
    services.append({
        "id": "flights",
        "label": "Flight search",
        "status": flight_status,
        "detail": flight_detail,
    })

    booking_ready = (
        str(getattr(config, "booking_mode", "disabled")).strip().lower() == "search_and_redirect"
        and bool(str(getattr(config, "booking_api_token", "")).strip())
        and bool(str(getattr(config, "booking_affiliate_id", "")).strip())
    )
    if booking_ready:
        hotel_status = "configured"
        hotel_detail = "Booking.com Demand API search-and-redirect is configured. Final booking is completed with the booking provider."
    elif cli_available:
        hotel_status = "legacy_provider"
        hotel_detail = "TRVL CLI is available for hotel search. Otherwise, Warik uses a Booking.com search handoff."
    else:
        hotel_status = "external_search_only"
        hotel_detail = "Booking.com Demand API is not enabled with partner credentials. Warik can provide an external search handoff."
    services.append({
        "id": "hotels",
        "label": "Hotel search",
        "status": hotel_status,
        "detail": hotel_detail,
    })

    services.append({
        "id": "rides",
        "label": "Airport transfers",
        "status": "handoff_only",
        "detail": "Uber and Ola handoff links are available. Live fares, vehicle availability and ride booking are not provided by Warik.",
    })
    services.append({
        "id": "rail_bus",
        "label": "Train and bus",
        "status": "handoff_only",
        "detail": "IRCTC and bus-provider search handoffs are available. Live seat inventory and ticket issuance are not provided by Warik.",
    })

    voice_enabled = bool(getattr(config, "voice_enabled", False))
    speech_configured = bool(
        str(getattr(config, "groq_api_key", "")).strip()
        or str(getattr(config, "gnani_api_key", "")).strip()
    )
    voice_status = (
        "configured" if voice_enabled and speech_configured
        else "missing_credentials" if voice_enabled
        else "disabled"
    )
    voice_detail = (
        "Voice transcription is enabled and a speech provider credential is configured."
        if voice_status == "configured"
        else "Voice is enabled, but neither GROQ_API_KEY nor GNANI_API_KEY is configured."
        if voice_status == "missing_credentials"
        else "Voice capture is disabled. Set VOICE_ENABLED=true and configure a server-side speech provider to enable it."
    )
    services.append({
        "id": "voice",
        "label": "Multilingual voice",
        "status": voice_status,
        "detail": voice_detail,
    })

    swiggy_mode = str(getattr(config, "swiggy_mode", "mock")).strip().lower()
    services.append({
        "id": "food",
        "label": "Food integrations",
        "status": "mock" if swiggy_mode == "mock" else "account_connection",
        "detail": (
            "Swiggy integration is in mock mode; results are not live."
            if swiggy_mode == "mock"
            else "Swiggy account authorization is managed separately in Connected services."
        ),
    })
    services.append({
        "id": "places",
        "label": "Maps and places",
        "status": "best_effort",
        "detail": "OpenStreetMap geocoding and place listings are best-effort public services, not guaranteed real-time inventory.",
    })

    return {
        "services": services,
        "note": "These statuses describe server configuration, not a live availability test. Prices and inventory are rechecked only when the relevant provider supports it.",
    }


@router.get("/health/capabilities")
def capability_status(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Expose provider readiness to the signed-in user without revealing secrets."""
    return build_capability_status()
