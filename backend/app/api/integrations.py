from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

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
from app.models import User


router = APIRouter(prefix="/integrations", tags=["integrations"])


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
    return connection_status(db, current_user.id)


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
