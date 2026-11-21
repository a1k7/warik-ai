import asyncio
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.integrations.google import oauth, service
from app.integrations.google.crypto import decrypt_secret
from app.models import User
from app.models.gmail_connection import GmailConnection, GmailOAuthTransaction


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.is_error = status_code >= 400

    def json(self):
        return self._data


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.responses = []
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.responses.pop(0)


def configure_google(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-google-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-google-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/api/integrations/gmail/oauth/callback")
    monkeypatch.setattr(settings, "google_frontend_return_url", "http://localhost:5173/settings")
    monkeypatch.setattr(settings, "google_token_encryption_key", Fernet.generate_key().decode("ascii"))


def make_user(db, email="gmail-test@example.com"):
    user = User(email=email, name="Gmail Test", password_hash="not-a-real-password-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_google_authorization_uses_readonly_scope_offline_and_pkce(db_session, monkeypatch):
    configure_google(monkeypatch)
    user = make_user(db_session)
    url = oauth.create_authorization(db_session, user.id)
    query = parse_qs(urlparse(url).query)
    state = query["state"][0]
    row = db_session.query(GmailOAuthTransaction).filter_by(user_id=user.id).one()

    assert query["scope"] == [oauth.GMAIL_READONLY_SCOPE]
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert row.state_hash == hashlib.sha256(state.encode()).hexdigest()
    assert row.state_hash != state
    assert decrypt_secret(row.code_verifier_ciphertext)


def test_google_callback_encrypts_tokens_and_binds_account_to_user(db_session, monkeypatch):
    configure_google(monkeypatch)
    user = make_user(db_session)
    auth_url = oauth.create_authorization(db_session, user.id)
    state = parse_qs(urlparse(auth_url).query)["state"][0]
    fake = FakeAsyncClient()
    fake.responses = [
        FakeResponse({"access_token": "access-value", "refresh_token": "refresh-value", "expires_in": 3600, "scope": oauth.GMAIL_READONLY_SCOPE}),
        FakeResponse({"emailAddress": "person@example.com"}),
    ]
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda *a, **kw: fake)

    completed_user_id = asyncio.run(oauth.complete_authorization(db_session, code="one-time-code", state=state))
    connection = db_session.query(GmailConnection).filter_by(user_id=user.id).one()

    assert completed_user_id == user.id
    assert connection.email_address == "person@example.com"
    assert connection.access_token_ciphertext != "access-value"
    assert decrypt_secret(connection.access_token_ciphertext) == "access-value"
    assert decrypt_secret(connection.refresh_token_ciphertext) == "refresh-value"
    assert oauth.connection_status(db_session, user.id)["permission"] == "read_only"
    assert len(fake.requests) == 2


def test_google_oauth_state_is_single_use(db_session, monkeypatch):
    configure_google(monkeypatch)
    user = make_user(db_session)
    auth_url = oauth.create_authorization(db_session, user.id)
    state = parse_qs(urlparse(auth_url).query)["state"][0]
    row = oauth._consume_transaction(db_session, state)
    assert row.consumed_at is not None
    with pytest.raises(oauth.GmailOAuthError, match="already used"):
        oauth._consume_transaction(db_session, state)


def test_google_connection_status_is_user_scoped(db_session, monkeypatch):
    configure_google(monkeypatch)
    first = make_user(db_session, "first-gmail@example.com")
    second = make_user(db_session, "second-gmail@example.com")
    connection = GmailConnection(
        user_id=first.id,
        email_address="first-gmail@example.com",
        access_token_ciphertext=oauth.encrypt_secret("first-access"),
        refresh_token_ciphertext=oauth.encrypt_secret("first-refresh"),
        scope=oauth.GMAIL_READONLY_SCOPE,
        expires_at=oauth.utcnow() + timedelta(hours=1),
        status="connected",
    )
    db_session.add(connection)
    db_session.commit()
    assert oauth.connection_status(db_session, first.id)["connected"] is True
    assert oauth.connection_status(db_session, second.id)["connected"] is False


def test_gmail_context_uses_metadata_format_and_does_not_fetch_body(monkeypatch):
    fake = FakeAsyncClient()
    fake.responses = [
        FakeResponse({"messages": [{"id": "msg-1"}]}),
        FakeResponse({
            "id": "msg-1",
            "snippet": "Your flight booking is confirmed",
            "payload": {"headers": [
                {"name": "Subject", "value": "IndiGo flight confirmation"},
                {"name": "From", "value": "airline@example.com"},
                {"name": "Date", "value": "Wed, 18 Nov 2026 10:00:00 +0000"},
            ]},
        }),
    ]
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda *a, **kw: fake)

    result = asyncio.run(service.list_travel_confirmations("access-token", max_results=5))

    assert result["permission"] == "read_only"
    assert result["content_persisted"] is False
    assert result["message_bodies_fetched"] is False
    assert result["items"][0]["category"] == "flight"
    detail_request = fake.requests[1]
    assert detail_request[2]["params"]["format"] == "metadata"
    assert "snippet" in result["items"][0]


def test_gmail_result_limit_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 25"):
        asyncio.run(service.list_travel_confirmations("token", max_results=100))
