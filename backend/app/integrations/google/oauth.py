"""Per-user Google OAuth lifecycle for read-only Gmail personal context."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.google.crypto import decrypt_secret, encrypt_secret
from app.models.gmail_connection import GmailConnection, GmailOAuthTransaction

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TRANSACTION_TTL_MINUTES = 10
REFRESH_EARLY_SECONDS = 60


class GmailOAuthError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _require_configuration() -> None:
    required = {
        "GOOGLE_CLIENT_ID": settings.google_client_id,
        "GOOGLE_CLIENT_SECRET": settings.google_client_secret,
        "GOOGLE_REDIRECT_URI": settings.google_redirect_uri,
        "GOOGLE_TOKEN_ENCRYPTION_KEY": settings.google_token_encryption_key,
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        raise GmailOAuthError("Google Gmail connection is not configured: " + ", ".join(missing))


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def create_authorization(db: Session, user_id: int) -> str:
    _require_configuration()
    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    transaction = GmailOAuthTransaction(
        user_id=user_id,
        state_hash=hashlib.sha256(state.encode("utf-8")).hexdigest(),
        code_verifier_ciphertext=encrypt_secret(verifier),
        redirect_uri=settings.google_redirect_uri.strip(),
        expires_at=utcnow() + timedelta(minutes=TRANSACTION_TTL_MINUTES),
    )
    db.add(transaction)
    db.commit()
    params = {
        "client_id": settings.google_client_id.strip(),
        "redirect_uri": settings.google_redirect_uri.strip(),
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _consume_transaction(db: Session, state: str) -> GmailOAuthTransaction:
    if not state or len(state) > 512:
        raise GmailOAuthError("Invalid or expired Google authorization state.")
    digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    transaction = (
        db.query(GmailOAuthTransaction)
        .filter(GmailOAuthTransaction.state_hash == digest)
        .with_for_update()
        .first()
    )
    if transaction is None:
        raise GmailOAuthError("Invalid or expired Google authorization state.")
    if transaction.consumed_at is not None:
        raise GmailOAuthError("This Google authorization callback was already used.")
    if _aware(transaction.expires_at) <= utcnow():
        transaction.consumed_at = utcnow()
        db.commit()
        raise GmailOAuthError("Google authorization request expired. Please reconnect.")
    transaction.consumed_at = utcnow()
    db.commit()
    return transaction


def _validate_token_response(data: object) -> dict:
    if not isinstance(data, dict):
        raise GmailOAuthError("Google returned an invalid token response.")
    access_token = data.get("access_token")
    expires_in = data.get("expires_in")
    if not isinstance(access_token, str) or not access_token:
        raise GmailOAuthError("Google token response did not contain an access token.")
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)):
        raise GmailOAuthError("Google token response contained an invalid expiry.")
    if expires_in <= 0 or expires_in > 86400:
        raise GmailOAuthError("Google token expiry is outside the accepted range.")
    refresh_token = data.get("refresh_token")
    if refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token):
        raise GmailOAuthError("Google returned an invalid refresh token.")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": int(expires_in),
        "scope": str(data.get("scope") or GMAIL_READONLY_SCOPE),
        "token_type": str(data.get("token_type") or "Bearer"),
    }


async def _exchange_code(code: str, verifier: str, redirect_uri: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id.strip(),
                    "client_secret": settings.google_client_secret.strip(),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
    except httpx.RequestError as exc:
        raise GmailOAuthError(f"Google token exchange failed ({type(exc).__name__}).") from None
    if response.is_error:
        raise GmailOAuthError(f"Google token exchange failed (HTTP {response.status_code}).")
    try:
        return _validate_token_response(response.json())
    except ValueError:
        raise GmailOAuthError("Google returned an invalid token response.") from None


async def _fetch_gmail_email(access_token: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.get(
                GMAIL_PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as exc:
        raise GmailOAuthError(f"Gmail profile lookup failed ({type(exc).__name__}).") from None
    if response.is_error:
        raise GmailOAuthError(f"Gmail profile lookup failed (HTTP {response.status_code}).")
    try:
        email = response.json().get("emailAddress")
    except (ValueError, AttributeError):
        email = None
    if not isinstance(email, str) or "@" not in email:
        raise GmailOAuthError("Google did not return a valid Gmail account address.")
    return email


async def complete_authorization(db: Session, *, code: str, state: str) -> int:
    if not code or len(code) > 4096:
        raise GmailOAuthError("Google did not return a valid authorization code.")
    transaction = _consume_transaction(db, state)
    verifier = decrypt_secret(transaction.code_verifier_ciphertext)
    token_data = await _exchange_code(code, verifier, transaction.redirect_uri)
    existing = (
        db.query(GmailConnection)
        .filter(GmailConnection.user_id == transaction.user_id)
        .with_for_update()
        .first()
    )
    refresh_token = token_data["refresh_token"]
    if not refresh_token and existing is not None:
        refresh_token = decrypt_secret(existing.refresh_token_ciphertext)
    if not refresh_token:
        raise GmailOAuthError("Google did not issue offline access. Reconnect and approve the requested permissions.")
    email_address = await _fetch_gmail_email(token_data["access_token"])
    values = {
        "email_address": email_address,
        "access_token_ciphertext": encrypt_secret(token_data["access_token"]),
        "refresh_token_ciphertext": encrypt_secret(refresh_token),
        "scope": token_data["scope"],
        "expires_at": utcnow() + timedelta(seconds=token_data["expires_in"]),
        "status": "connected",
    }
    if existing is None:
        db.add(GmailConnection(user_id=transaction.user_id, **values))
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    db.commit()
    return transaction.user_id


async def refresh_connection(db: Session, user_id: int) -> str:
    _require_configuration()
    connection = (
        db.query(GmailConnection)
        .filter(GmailConnection.user_id == user_id)
        .with_for_update()
        .first()
    )
    if connection is None or connection.status != "connected":
        raise GmailOAuthError("Gmail is not connected. Please authorize again.")
    refresh_token = decrypt_secret(connection.refresh_token_ciphertext)
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id.strip(),
                    "client_secret": settings.google_client_secret.strip(),
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if response.is_error:
            raise GmailOAuthError(f"Google token refresh failed (HTTP {response.status_code}).")
        token_data = _validate_token_response(response.json())
    except Exception as exc:
        connection.status = "reauthorization_required"
        db.commit()
        if isinstance(exc, GmailOAuthError):
            raise
        raise GmailOAuthError("Google token refresh failed. Please reconnect Gmail.") from None
    connection.access_token_ciphertext = encrypt_secret(token_data["access_token"])
    if token_data["refresh_token"]:
        connection.refresh_token_ciphertext = encrypt_secret(token_data["refresh_token"])
    connection.scope = token_data["scope"] or connection.scope
    connection.expires_at = utcnow() + timedelta(seconds=token_data["expires_in"])
    connection.status = "connected"
    db.commit()
    return token_data["access_token"]


async def get_valid_access_token(db: Session, user_id: int) -> str:
    connection = (
        db.query(GmailConnection)
        .filter(GmailConnection.user_id == user_id)
        .first()
    )
    if connection is None or connection.status != "connected":
        raise GmailOAuthError("Connect your Gmail account first.")
    if _aware(connection.expires_at) <= utcnow() + timedelta(seconds=REFRESH_EARLY_SECONDS):
        return await refresh_connection(db, user_id)
    return decrypt_secret(connection.access_token_ciphertext)


async def disconnect_user(db: Session, user_id: int) -> None:
    connection = (
        db.query(GmailConnection)
        .filter(GmailConnection.user_id == user_id)
        .with_for_update()
        .first()
    )
    if connection is None:
        return
    try:
        refresh_token = decrypt_secret(connection.refresh_token_ciphertext)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            await client.post(GOOGLE_REVOKE_URL, data={"token": refresh_token})
    except Exception:
        # Local credentials are deleted even if remote revocation is unavailable.
        pass
    db.delete(connection)
    db.commit()


def connection_status(db: Session, user_id: int) -> dict:
    connection = (
        db.query(GmailConnection)
        .filter(GmailConnection.user_id == user_id)
        .first()
    )
    if connection is None:
        return {"connected": False, "status": "disconnected", "permission": "read_only"}
    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "email_address": connection.email_address,
        "expires_at": _aware(connection.expires_at).isoformat(),
        "scope": connection.scope or "",
        "permission": "read_only",
    }
