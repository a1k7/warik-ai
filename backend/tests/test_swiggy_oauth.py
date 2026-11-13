import asyncio
import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.integrations.swiggy import oauth
from app.integrations.swiggy.crypto import decrypt_secret
from app.models import User
from app.models.swiggy_connection import (
    SwiggyConnection,
    SwiggyOAuthTransaction,
)


def configure_oauth(monkeypatch):
    """Provide isolated test-only OAuth configuration."""
    monkeypatch.setattr(settings, "swiggy_client_id", "test-client-id")
    monkeypatch.setattr(
        settings,
        "swiggy_redirect_uri",
        "http://localhost:8000/api/integrations/swiggy/oauth/callback",
    )
    monkeypatch.setattr(
        settings,
        "swiggy_token_encryption_key",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setattr(
        settings,
        "swiggy_authorize_url",
        "https://example.test/auth/authorize",
    )
    monkeypatch.setattr(
        settings,
        "swiggy_token_url",
        "https://example.test/auth/token",
    )
    monkeypatch.setattr(
        settings,
        "swiggy_logout_url",
        "https://example.test/auth/logout",
    )
    monkeypatch.setattr(settings, "swiggy_oauth_scope", "mcp:tools")


def make_user(db, email="oauth-test@example.com"):
    user = User(
        email=email,
        name="OAuth Test User",
        password_hash="not-a-real-password-hash",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class FakeAsyncClient:
    """Mock httpx.AsyncClient without making network requests."""

    def __init__(self, *args, **kwargs):
        self.response = FakeResponse(
            {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "token_type": "Bearer",
                "scope": "mcp:tools",
                "expires_in": 432000,
            }
        )
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.response


def test_pkce_pair_uses_s256():
    verifier, challenge = oauth._pkce_pair()

    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    assert verifier
    assert len(verifier) >= 43
    assert challenge == expected


def test_create_authorization_stores_hashed_state_and_encrypted_verifier(
    db_session, monkeypatch
):
    configure_oauth(monkeypatch)
    user = make_user(db_session)

    authorization_url = oauth.create_authorization(db_session, user.id)

    parsed = urlparse(authorization_url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "example.test"
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["test-client-id"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["mcp:tools"]

    state = params["state"][0]
    transaction = (
        db_session.query(SwiggyOAuthTransaction)
        .filter_by(user_id=user.id)
        .one()
    )

    assert transaction.state_hash == hashlib.sha256(
        state.encode("utf-8")
    ).hexdigest()
    assert transaction.state_hash != state

    verifier = decrypt_secret(transaction.code_verifier_ciphertext)
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    assert params["code_challenge"] == [expected_challenge]
    assert "code_verifier" not in params


def test_invalid_state_is_rejected(db_session, monkeypatch):
    configure_oauth(monkeypatch)
    user = make_user(db_session)

    oauth.create_authorization(db_session, user.id)

    with pytest.raises(oauth.SwiggyOAuthError, match="Invalid or expired"):
        oauth._consume_transaction(db_session, "incorrect-state")


def test_state_cannot_be_replayed(db_session, monkeypatch):
    configure_oauth(monkeypatch)
    user = make_user(db_session)

    authorization_url = oauth.create_authorization(db_session, user.id)
    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    transaction = oauth._consume_transaction(db_session, state)

    assert transaction.consumed_at is not None

    with pytest.raises(oauth.SwiggyOAuthError, match="already used"):
        oauth._consume_transaction(db_session, state)


def test_expired_state_is_rejected(db_session, monkeypatch):
    configure_oauth(monkeypatch)
    user = make_user(db_session)

    transaction = SwiggyOAuthTransaction(
        user_id=user.id,
        state_hash=hashlib.sha256(b"expired-state").hexdigest(),
        code_verifier_ciphertext=oauth.encrypt_secret("test-verifier"),
        redirect_uri=settings.swiggy_redirect_uri,
        client_id=settings.swiggy_client_id,
        expires_at=oauth.utcnow() - timedelta(minutes=1),
    )
    db_session.add(transaction)
    db_session.commit()

    with pytest.raises(oauth.SwiggyOAuthError, match="expired"):
        oauth._consume_transaction(db_session, "expired-state")

    db_session.refresh(transaction)
    assert transaction.consumed_at is not None


def test_complete_authorization_encrypts_and_persists_tokens(
    db_session, monkeypatch
):
    configure_oauth(monkeypatch)
    user = make_user(db_session)

    authorization_url = oauth.create_authorization(db_session, user.id)
    params = parse_qs(urlparse(authorization_url).query)
    state = params["state"][0]

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda *a, **kw: fake_client)

    completed_user_id = asyncio.run(
        oauth.complete_authorization(
            db_session,
            code="test-authorization-code",
            state=state,
        )
    )

    assert completed_user_id == user.id

    connection = (
        db_session.query(SwiggyConnection)
        .filter_by(user_id=user.id)
        .one()
    )

    assert connection.status == "connected"
    assert connection.access_token_ciphertext != "new-access-token"
    assert connection.refresh_token_ciphertext != "new-refresh-token"
    assert decrypt_secret(connection.access_token_ciphertext) == "new-access-token"
    assert decrypt_secret(connection.refresh_token_ciphertext) == "new-refresh-token"

    assert len(fake_client.requests) == 1
    url, request = fake_client.requests[0]
    assert url == settings.swiggy_token_url
    assert request["json"]["grant_type"] == "authorization_code"
    assert request["json"]["code"] == "test-authorization-code"
    assert request["json"]["client_id"] == "test-client-id"
    assert request["json"]["redirect_uri"] == settings.swiggy_redirect_uri
    assert request["json"]["code_verifier"]


def test_refresh_rotates_and_persists_both_tokens(db_session, monkeypatch):
    configure_oauth(monkeypatch)
    user = make_user(db_session)

    connection = SwiggyConnection(
        user_id=user.id,
        access_token_ciphertext=oauth.encrypt_secret("old-access-token"),
        refresh_token_ciphertext=oauth.encrypt_secret("old-refresh-token"),
        token_type="Bearer",
        scope="mcp:tools",
        expires_at=oauth.utcnow() - timedelta(minutes=1),
        status="connected",
    )
    db_session.add(connection)
    db_session.commit()

    fake_client = FakeAsyncClient()
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda *a, **kw: fake_client)

    access_token = asyncio.run(
        oauth.refresh_connection(db_session, user.id)
    )

    db_session.refresh(connection)

    assert access_token == "new-access-token"
    assert decrypt_secret(connection.access_token_ciphertext) == "new-access-token"
    assert decrypt_secret(connection.refresh_token_ciphertext) == "new-refresh-token"
    assert connection.status == "connected"

    assert len(fake_client.requests) == 1
    _, request = fake_client.requests[0]
    assert request["json"] == {
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh-token",
    }


def test_connection_status_is_isolated_per_user(db_session, monkeypatch):
    configure_oauth(monkeypatch)
    first_user = make_user(db_session, "first@example.com")
    second_user = make_user(db_session, "second@example.com")

    connection = SwiggyConnection(
        user_id=first_user.id,
        access_token_ciphertext=oauth.encrypt_secret("first-access"),
        refresh_token_ciphertext=oauth.encrypt_secret("first-refresh"),
        token_type="Bearer",
        scope="mcp:tools",
        expires_at=oauth.utcnow() + timedelta(hours=1),
        status="connected",
    )
    db_session.add(connection)
    db_session.commit()

    first_status = oauth.connection_status(db_session, first_user.id)
    second_status = oauth.connection_status(db_session, second_user.id)

    assert first_status["connected"] is True
    assert first_status["status"] == "connected"
    assert second_status == {
        "connected": False,
        "status": "disconnected",
    }
