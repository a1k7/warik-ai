"""TTS tests — uses httpx.MockTransport, so no real Gnani credits are spent."""

import uuid

import httpx
import pytest

from app.core.config import settings
from app.main import app
from app.models import VoiceUsage
from app.services.gnani_tts import GnaniTTSClient
from app.services.tts_provider import GnaniTTSProvider, get_tts_provider

DUMMY_WAV = b"RIFF" + (36 + 100).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 100


def _login_token(client, email="tts@example.com") -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "name": "TTS", "password": "password123"},
    )
    if response.status_code == 409:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mock_provider(handler, voice="Pranav", model="timbre"):
    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)

    return GnaniTTSProvider(
        GnaniTTSClient(
            api_key="test-key",
            tts_url="https://api.gnani.ai/v1/tts/inference",
            default_voice=voice,
            default_model=model,
            client_factory=factory,
        )
    )


def test_tts_disabled_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", False)
    token = _login_token(client)
    response = client.post(
        "/api/voice/speak",
        headers=_auth(token),
        json={"text": "Hello world"},
    )
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"].lower()


def test_tts_enabled_but_missing_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "")
    token = _login_token(client)
    response = client.post(
        "/api/voice/speak",
        headers=_auth(token),
        json={"text": "Hello world"},
    )
    assert response.status_code == 503
    assert "GNANI_API_KEY" in response.json()["detail"]


def test_tts_success_and_usage_increment(client, monkeypatch, db_session, tmp_path):
    # Force the cache to use a temporary directory so this test is isolated
    monkeypatch.setattr("app.services.tts_provider.CACHE_DIR", tmp_path)

    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")
    monkeypatch.setattr(settings, "voice_tts_char_limit", 100)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, content=DUMMY_WAV, headers={"content-type": "audio/wav"})

    app.dependency_overrides[get_tts_provider] = lambda: _mock_provider(handler)
    try:
        token = _login_token(client)
        # Use a unique string so it is NEVER cached from a previous run
        text = f"This is a test {uuid.uuid4()}."
        response = client.post(
            "/api/voice/speak",
            headers=_auth(token),
            json={"text": text},
        )
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)

    assert response.status_code == 200, response.text
    assert response.content == DUMMY_WAV
    assert response.headers["content-type"] == "audio/wav"

    rows = db_session.query(VoiceUsage).all()
    assert len(rows) == 1
    assert rows[0].characters_used == len(text)
    assert rows[0].tts_requests_count == 1


def test_tts_caching_saves_credits(client, monkeypatch, db_session, tmp_path):
    monkeypatch.setattr("app.services.tts_provider.CACHE_DIR", tmp_path)

    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, content=DUMMY_WAV, headers={"content-type": "audio/wav"})

    app.dependency_overrides[get_tts_provider] = lambda: _mock_provider(handler)
    try:
        token = _login_token(client)
        text = f"Cached unique string {uuid.uuid4()}"

        # First call (misses cache, calls Gnani)
        r1 = client.post("/api/voice/speak", headers=_auth(token), json={"text": text})
        # Second call (hits cache, skips Gnani)
        r2 = client.post("/api/voice/speak", headers=_auth(token), json={"text": text})
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert call_count["n"] == 1  # Gnani called exactly once

    rows = db_session.query(VoiceUsage).all()
    assert len(rows) == 1
    assert rows[0].characters_used == len(text)  # only billed once
    assert rows[0].tts_requests_count == 1


def test_tts_limit_enforced(client, monkeypatch, db_session, tmp_path):
    monkeypatch.setattr("app.services.tts_provider.CACHE_DIR", tmp_path)

    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")
    monkeypatch.setattr(settings, "voice_tts_char_limit", 10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=DUMMY_WAV)

    app.dependency_overrides[get_tts_provider] = lambda: _mock_provider(handler)
    try:
        token = _login_token(client)
        # 15 chars > limit of 10
        response = client.post(
            "/api/voice/speak",
            headers=_auth(token),
            json={"text": "Too many chars"},
        )
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)

    assert response.status_code == 429
    assert db_session.query(VoiceUsage).count() == 0