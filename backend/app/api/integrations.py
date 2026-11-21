from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import settings
from app.database.session import get_db
from app.integrations.status import get_provider_status
from app.integrations.swiggy.client import SwiggyMCPError
from app.integrations.swiggy.oauth import (
    SwiggyOAuthError,
    complete_authorization,
    connection_status,
    create_authorization,
    disconnect_user,
    get_valid_access_token,
)
from app.integrations.swiggy.service import get_addresses, search_restaurants
from app.integrations.google.oauth import (
    GmailOAuthError,
    complete_authorization as complete_gmail_authorization,
    connection_status as gmail_connection_status,
    create_authorization as create_gmail_authorization,
    disconnect_user as disconnect_gmail_user,
    get_valid_access_token as get_valid_gmail_access_token,
)
from app.integrations.google.service import GmailAPIError, list_travel_confirmations
from app.models import Conversation, User


class GmailTravelEvidenceImportRequest(BaseModel):
    conversation_id: int
    max_results: int = Field(default=20, ge=1, le=25)


class GmailTravelBookingConfirmRequest(BaseModel):
    conversation_id: int
    message_id: str = Field(min_length=1, max_length=200)


router = APIRouter(prefix="/integrations", tags=["integrations"])


def _gmail_frontend_redirect(result: str) -> RedirectResponse:
    base = settings.google_frontend_return_url.rstrip("/")
    return RedirectResponse(url=f"{base}?gmail={result}", status_code=303)


def _frontend_redirect(result: str) -> RedirectResponse:
    base = settings.swiggy_frontend_return_url.rstrip("/")
    return RedirectResponse(
        url=f"{base}?swiggy={result}",
        status_code=303,
    )


@router.get("")
def list_integrations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    providers = get_provider_status()
    providers["swiggy"] = {
        **providers.get("swiggy", {}),
        **connection_status(db, current_user.id),
    }
    return {"providers": providers, "user_id": current_user.id}


@router.get("/swiggy/status")
def swiggy_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    result = connection_status(db, current_user.id)
    result["mode"] = settings.swiggy_mode.strip().lower()
    result["live_services_enabled"] = (
        result["connected"] and settings.swiggy_mode.strip().lower() == "production"
    )
    return result


@router.post("/swiggy/oauth/start")
def swiggy_oauth_start(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return {"authorization_url": create_authorization(db, current_user.id)}
    except SwiggyOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/swiggy/oauth/callback")
async def swiggy_oauth_callback(
    code: str | None = Query(default=None, max_length=4096),
    state: str = Query(..., min_length=20, max_length=512),
    error: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    if error:
        # Consume the transaction even when the user denies authorization.
        from app.integrations.swiggy.oauth import _consume_transaction

        try:
            _consume_transaction(db, state)
        except SwiggyOAuthError:
            pass
        return _frontend_redirect("error")

    if not code:
        return _frontend_redirect("error")

    try:
        await complete_authorization(db, code=code, state=state)
        return _frontend_redirect("connected")
    except SwiggyOAuthError:
        return _frontend_redirect("error")
    except Exception:
        return _frontend_redirect("error")


@router.delete("/swiggy")
async def swiggy_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    await disconnect_user(db, current_user.id)
    return {"connected": False, "status": "disconnected"}


@router.get("/swiggy/addresses")
async def swiggy_addresses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        token = None
        if settings.swiggy_mode.strip().lower() == "production":
            token = await get_valid_access_token(db, current_user.id)
        return await get_addresses(access_token=token)
    except (SwiggyMCPError, SwiggyOAuthError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/swiggy/restaurants/search")
async def swiggy_restaurant_search(
    query: str = Query(..., min_length=2, max_length=100),
    address_id: str = Query(..., min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        token = None
        if settings.swiggy_mode.strip().lower() == "production":
            token = await get_valid_access_token(db, current_user.id)
        return await search_restaurants(
            query=query,
            address_id=address_id,
            access_token=token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (SwiggyMCPError, SwiggyOAuthError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Gmail — read-only personal context. These endpoints never mutate mailbox data.
@router.get("/gmail/status")
def gmail_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return gmail_connection_status(db, current_user.id)


@router.post("/gmail/oauth/start")
def gmail_oauth_start(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return {"authorization_url": create_gmail_authorization(db, current_user.id)}
    except GmailOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/gmail/oauth/callback")
async def gmail_oauth_callback(
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    if error or not code or not state:
        if state:
            from app.integrations.google.oauth import _consume_transaction
            try:
                _consume_transaction(db, state)
            except GmailOAuthError:
                pass
        return _gmail_frontend_redirect("error")
    try:
        await complete_gmail_authorization(db, code=code, state=state)
        return _gmail_frontend_redirect("connected")
    except GmailOAuthError:
        return _gmail_frontend_redirect("error")
    except Exception:
        return _gmail_frontend_redirect("error")


@router.delete("/gmail")
async def gmail_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    await disconnect_gmail_user(db, current_user.id)
    return {"connected": False, "status": "disconnected", "permission": "read_only"}


@router.get("/gmail/travel-confirmations")
async def gmail_travel_confirmations(
    max_results: int = Query(default=20, ge=1, le=25),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        token = await get_valid_gmail_access_token(db, current_user.id)
        return await list_travel_confirmations(token, max_results=max_results)
    except GmailOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (GmailAPIError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/gmail/travel-confirmations/import")
async def import_gmail_travel_evidence(
    request: GmailTravelEvidenceImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == request.conversation_id,
            Conversation.user_id == current_user.id,
        )
        .one_or_none()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    try:
        token = await get_valid_gmail_access_token(db, current_user.id)
        result = await list_travel_confirmations(token, max_results=request.max_results)
    except GmailOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (GmailAPIError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    from app.services.context.travel_artifacts import attach_gmail_booking_evidence
    imported = attach_gmail_booking_evidence(
        conversation,
        items=result.get("items") or [],
        retrieved_at=result.get("retrieved_at"),
    )
    if imported:
        db.commit()
    return {
        **result,
        "imported_booking_evidence_count": imported,
        "booking_evidence_status": "needs_user_review",
        "note": "Email matches are evidence candidates, not confirmed bookings. Review and explicitly confirm each one.",
    }


@router.post("/gmail/travel-confirmations/confirm")
def confirm_gmail_travel_booking(
    request: GmailTravelBookingConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == request.conversation_id,
            Conversation.user_id == current_user.id,
        )
        .one_or_none()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    from app.services.context.travel_artifacts import confirm_gmail_booking_in_mission
    confirmed = confirm_gmail_booking_in_mission(
        conversation,
        message_id=request.message_id,
    )
    if confirmed is None:
        raise HTTPException(
            status_code=409,
            detail="No pending Gmail booking evidence was found for that message in this travel mission.",
        )
    db.commit()
    return {
        "status": "confirmed_by_user",
        "booking": confirmed,
        "note": "This record is user-confirmed from Gmail metadata; it is not independently verified with the travel provider.",
    }
