"""Voice STT tests — every test runs without a real Gnani key and without
spending credits. Gnani is simulated with httpx.MockTransport."""

import io

import httpx
import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models import User, VoiceUsage
from app.services.gnani_stt import GnaniSTTClient, GnaniSTTError
from app.services.stt_provider import (
    GnaniSTTProvider,
    NullSTTProvider,
    get_stt_provider,
)


def _make_user(db, email="voice@example.com") -> User:
    user = User(email=email, name="Voice", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login_token(client, email="voice@example.com") -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "name": "Voice", "password": "password123"},
    )
    assert response.status_code in (201, 409), response.text
    if response.status_code == 409:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wav_bytes(seconds: int = 1, sample_rate: int = 16000) -> bytes:
    """Minimal valid WAV header + silent PCM data."""
    channels = 1
    bits = 16
    byte_rate = sample_rate * channels * bits // 8
    data_size = byte_rate * seconds
    header = (
        b"RIFF"
        + (36 + data_size).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")  # PCM
        + channels.to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + byte_rate.to_bytes(4, "little")
        + (channels * bits // 8).to_bytes(2, "little")
        + bits.to_bytes(2, "little")
        + b"data"
        + data_size.to_bytes(4, "little")
    )
    return header + b"\x00" * data_size


def _mock_provider(handler):
    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)

    return GnaniSTTProvider(
        GnaniSTTClient(
            api_key="test-key",
            stt_url="https://api.vachana.ai/stt/v3",
            client_factory=factory,
        )
    )


def test_voice_disabled_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", False)
    token = _login_token(client)
    response = client.post(
        "/api/voice/transcribe",
        headers=_auth(token),
        files={"audio": ("a.wav", _wav_bytes(1), "audio/wav")},
        data={"language_code": "en-IN"},
    )
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"].lower()


def test_voice_enabled_but_missing_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "")
    token = _login_token(client)
    response = client.post(
        "/api/voice/transcribe",
        headers=_auth(token),
        files={"audio": ("a.wav", _wav_bytes(1), "audio/wav")},
        data={"language_code": "en-IN"},
    )
    assert response.status_code == 503
    assert "GNANI_API_KEY" in response.json()["detail"]


def test_invalid_language_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")
    token = _login_token(client)
    response = client.post(
        "/api/voice/transcribe",
        headers=_auth(token),
        files={"audio": ("a.wav", _wav_bytes(1), "audio/wav")},
        data={"language_code": "xx-IN"},
    )
    assert response.status_code == 400
    assert "Unsupported language_code" in response.json()["detail"]


def test_file_too_large_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")
    monkeypatch.setattr(settings, "voice_max_upload_bytes", 100)
    token = _login_token(client)
    response = client.post(
        "/api/voice/transcribe",
        headers=_auth(token),
        files={"audio": ("a.wav", _wav_bytes(2), "audio/wav")},
        data={"language_code": "en-IN"},
    )
    assert response.status_code == 413


def test_transcription_success(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")
    monkeypatch.setattr(settings, "voice_usage_limit_seconds", 300)
    monkeypatch.setattr(settings, "voice_max_duration_seconds", 30)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key-ID"] == "test-key"
        body = request.read()
        assert b"language_code" in body
        assert b"transcribe" in body
        assert b"itn_native_numerals" in body
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req_test_123",
                "timestamp": "20261031_120000.000",
                "transcript": "remind me to study at 7 pm",
            },
        )

    app.dependency_overrides[get_stt_provider] = lambda: _mock_provider(handler)
    try:
        token = _login_token(client)
        response = client.post(
            "/api/voice/transcribe",
            headers=_auth(token),
            files={"audio": ("a.wav", _wav_bytes(1), "audio/wav")},
            data={"language_code": "en-IN", "duration_seconds": "1"},
        )
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] == "remind me to study at 7 pm"
    assert body["request_id"] == "req_test_123"
    assert body["language_code"] == "en-IN"
    assert body["usage_seconds_used"] == 1

    rows = db_session.query(VoiceUsage).all()
    assert len(rows) == 1
    assert rows[0].seconds_used == 1
    assert rows[0].requests_count == 1


def test_gnani_error_maps_to_502(client, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    app.dependency_overrides[get_stt_provider] = lambda: _mock_provider(handler)
    try:
        token = _login_token(client)
        response = client.post(
            "/api/voice/transcribe",
            headers=_auth(token),
            files={"audio": ("a.wav", _wav_bytes(1), "audio/wav")},
            data={"language_code": "en-IN"},
        )
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)

    assert response.status_code == 502


def test_usage_limit_enforced_before_api_call(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.setattr(settings, "gnani_api_key", "test")
    monkeypatch.setattr(settings, "voice_usage_limit_seconds", 1)

    called = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["count"] += 1
        return httpx.Response(
            200,
            json={"success": True, "request_id": "x", "transcript": "hi"},
        )

    app.dependency_overrides[get_stt_provider] = lambda: _mock_provider(handler)
    try:
        token = _login_token(client)
        # Use duration_seconds=30 so pre-check estimates 30 > limit of 1.
        response = client.post(
            "/api/voice/transcribe",
            headers=_auth(token),
            files={"audio": ("a.wav", _wav_bytes(1), "audio/wav")},
            data={"language_code": "en-IN", "duration_seconds": "30"},
        )
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)

    assert response.status_code == 429
    assert called["count"] == 0  # Gnani never called
    assert db_session.query(VoiceUsage).count() == 0