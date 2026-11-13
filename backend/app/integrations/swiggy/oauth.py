"""Per-user Swiggy OAuth 2.1 authorization-code + PKCE lifecycle."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.swiggy.crypto import encrypt_secret, decrypt_secret
from app.models.swiggy_connection import (
    SwiggyConnection,
    SwiggyOAuthTransaction,
)


TRANSACTION_TTL_MINUTES = 10
REFRESH_EARLY_SECONDS = 60


class SwiggyOAuthError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """SQLite may return naive datetimes for timezone-aware columns."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _require_oauth_configuration() -> None:
    if not settings.swiggy_client_id.strip():
        raise SwiggyOAuthError("Swiggy OAuth client is not configured.")
    if not settings.swiggy_redirect_uri.strip():
        raise SwiggyOAuthError("Swiggy OAuth redirect URI is not configured.")
    if not settings.swiggy_token_encryption_key.strip():
        raise SwiggyOAuthError("Swiggy credential encryption is not configured.")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def create_authorization(db: Session, user_id: int) -> str:
    """Create a short-lived transaction and return the provider authorization URL."""
    _require_oauth_configuration()

    state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    verifier, challenge = _pkce_pair()

    transaction = SwiggyOAuthTransaction(
        user_id=user_id,
        state_hash=state_hash,
        code_verifier_ciphertext=encrypt_secret(verifier),
        redirect_uri=settings.swiggy_redirect_uri.strip(),
        client_id=settings.swiggy_client_id.strip(),
        expires_at=utcnow() + timedelta(minutes=TRANSACTION_TTL_MINUTES),
    )

    db.add(transaction)
    db.commit()

    params = {
        "response_type": "code",
        "client_id": settings.swiggy_client_id.strip(),
        "redirect_uri": settings.swiggy_redirect_uri.strip(),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": settings.swiggy_oauth_scope.strip() or "mcp:tools",
    }

    return f"{settings.swiggy_authorize_url}?{urlencode(params)}"


def _consume_transaction(db: Session, state: str) -> SwiggyOAuthTransaction:
    if not state or len(state) > 512:
        raise SwiggyOAuthError("Invalid or expired Swiggy authorization state.")

    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    transaction = (
        db.query(SwiggyOAuthTransaction)
        .filter(SwiggyOAuthTransaction.state_hash == state_hash)
        .with_for_update()
        .first()
    )

    if transaction is None:
        raise SwiggyOAuthError("Invalid or expired Swiggy authorization state.")

    if transaction.consumed_at is not None:
        raise SwiggyOAuthError("This Swiggy authorization callback was already used.")

    if _aware(transaction.expires_at) <= utcnow():
        transaction.consumed_at = utcnow()
        db.commit()
        raise SwiggyOAuthError("Swiggy authorization request expired. Please reconnect.")

    # Consume before the network exchange so concurrent callbacks cannot replay it.
    transaction.consumed_at = utcnow()
    db.commit()
    return transaction


async def _exchange_code(
    *,
    code: str,
    verifier: str,
    client_id: str,
    redirect_uri: str,
) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
        response = await client.post(
            settings.swiggy_token_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    if response.status_code >= 400:
        raise SwiggyOAuthError("Swiggy authorization-code exchange failed.")

    try:
        data = response.json()
    except ValueError as exc:
        raise SwiggyOAuthError("Swiggy returned an invalid token response.") from exc

    return _validate_token_response(data)


def _validate_token_response(data: object) -> dict:
    if not isinstance(data, dict):
        raise SwiggyOAuthError("Swiggy returned an invalid token response.")

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    if not isinstance(access_token, str) or not access_token:
        raise SwiggyOAuthError("Swiggy token response did not contain an access token.")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise SwiggyOAuthError("Swiggy token response did not contain a refresh token.")
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)):
        raise SwiggyOAuthError("Swiggy token response contained an invalid expiry.")
    if expires_in <= 0 or expires_in > 60 * 60 * 24 * 60:
        raise SwiggyOAuthError("Swiggy token expiry is outside the accepted range.")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": str(data.get("token_type") or "Bearer"),
        "scope": str(data.get("scope") or ""),
        "expires_in": int(expires_in),
    }


async def complete_authorization(
    db: Session,
    *,
    code: str,
    state: str,
) -> int:
    if not code or len(code) > 4096:
        raise SwiggyOAuthError("Swiggy did not return a valid authorization code.")

    transaction = _consume_transaction(db, state)
    verifier = decrypt_secret(transaction.code_verifier_ciphertext)

    token_data = await _exchange_code(
        code=code,
        verifier=verifier,
        client_id=transaction.client_id,
        redirect_uri=transaction.redirect_uri,
    )

    connection = (
        db.query(SwiggyConnection)
        .filter(SwiggyConnection.user_id == transaction.user_id)
        .with_for_update()
        .first()
    )

    values = {
        "access_token_ciphertext": encrypt_secret(token_data["access_token"]),
        "refresh_token_ciphertext": encrypt_secret(token_data["refresh_token"]),
        "token_type": token_data["token_type"],
        "scope": token_data["scope"],
        "expires_at": utcnow() + timedelta(seconds=token_data["expires_in"]),
        "status": "connected",
    }

    if connection is None:
        connection = SwiggyConnection(user_id=transaction.user_id, **values)
        db.add(connection)
    else:
        for key, value in values.items():
            setattr(connection, key, value)

    db.commit()
    return transaction.user_id


async def refresh_connection(db: Session, user_id: int) -> str:
    """Refresh a user's credentials and atomically persist the rotated tokens."""
    _require_oauth_configuration()

    connection = (
        db.query(SwiggyConnection)
        .filter(SwiggyConnection.user_id == user_id)
        .with_for_update()
        .first()
    )

    if connection is None or connection.status != "connected":
        raise SwiggyOAuthError("Swiggy is not connected. Please authorize again.")

    refresh_token = decrypt_secret(connection.refresh_token_ciphertext)

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.post(
                settings.swiggy_token_url,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/json"},
            )

        if response.status_code >= 400:
            raise SwiggyOAuthError("Swiggy session could not be refreshed.")

        token_data = _validate_token_response(response.json())

    except Exception as exc:
        connection.status = "reauthorization_required"
        db.commit()
        if isinstance(exc, SwiggyOAuthError):
            raise
        raise SwiggyOAuthError("Swiggy session could not be refreshed.") from exc

    # Persist both rotated tokens in one database transaction.
    connection.access_token_ciphertext = encrypt_secret(token_data["access_token"])
    connection.refresh_token_ciphertext = encrypt_secret(token_data["refresh_token"])
    connection.token_type = token_data["token_type"]
    connection.scope = token_data["scope"] or connection.scope
    connection.expires_at = utcnow() + timedelta(seconds=token_data["expires_in"])
    connection.status = "connected"
    db.commit()

    return token_data["access_token"]


async def get_valid_access_token(db: Session, user_id: int) -> str:
    connection = (
        db.query(SwiggyConnection)
        .filter(SwiggyConnection.user_id == user_id)
        .first()
    )

    if connection is None or connection.status != "connected":
        raise SwiggyOAuthError("Connect your Swiggy account first.")

    if _aware(connection.expires_at) <= utcnow() + timedelta(
        seconds=REFRESH_EARLY_SECONDS
    ):
        return await refresh_connection(db, user_id)

    return decrypt_secret(connection.access_token_ciphertext)


async def disconnect_user(db: Session, user_id: int) -> None:
    connection = (
        db.query(SwiggyConnection)
        .filter(SwiggyConnection.user_id == user_id)
        .with_for_update()
        .first()
    )

    if connection is None:
        return

    # Remove local credentials even if remote revocation is unavailable.
    try:
        access_token = decrypt_secret(connection.access_token_ciphertext)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            await client.post(
                settings.swiggy_logout_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except Exception:
        # Do not retain credentials merely because remote logout failed.
        pass

    db.delete(connection)
    db.commit()


def connection_status(db: Session, user_id: int) -> dict:
    connection = (
        db.query(SwiggyConnection)
        .filter(SwiggyConnection.user_id == user_id)
        .first()
    )

    if connection is None:
        return {"connected": False, "status": "disconnected"}

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "expires_at": _aware(connection.expires_at).isoformat(),
        "scope": connection.scope or "",
    }
