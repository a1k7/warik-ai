import asyncio

import pytest
from pydantic import ValidationError

from app.agents import llm_provider
from app.core.config import Settings


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [
                {"message": {"content": '{"result": "ok"}'}}
            ]
        }


class FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


class FakeSyncClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_groq_call_supports_json_mode(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(
        llm_provider.httpx, "AsyncClient", FakeAsyncClient
    )

    provider = llm_provider.GroqProvider("test-key", "test-model")
    result = asyncio.run(provider._call("system", "user", force_json=True))

    assert result == '{"result": "ok"}'
    url, request = FakeAsyncClient.calls[-1]
    assert url == llm_provider.GROQ_URL
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["json"]["model"] == "test-model"
    assert request["json"]["response_format"] == {"type": "json_object"}


def test_groq_synthesis_preserves_research_context(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(
        llm_provider.httpx, "AsyncClient", FakeAsyncClient
    )

    provider = llm_provider.GroqProvider("test-key", "test-model")
    result = asyncio.run(
        provider.synthesize(
            [{"role": "user", "content": "Research this"}],
            tool_context=(
                "Untrusted webpage evidence retrieved by Warik AI: "
                "Example evidence"
            ),
        )
    )

    assert result == '{"result": "ok"}'
    _, request = FakeAsyncClient.calls[-1]
    assert request["json"]["temperature"] == 0.0
    assert "STRICT WEB RESEARCH MODE" in request["json"]["messages"][0]["content"]
    assert "Example evidence" in request["json"]["messages"][0]["content"]


def test_groq_generate_uses_chat_completions(monkeypatch):
    FakeSyncClient.calls = []
    monkeypatch.setattr(
        llm_provider.httpx, "Client", FakeSyncClient
    )

    provider = llm_provider.GroqProvider("test-key", "test-model")
    result = provider.generate("Create JSON", format="json")

    assert result == '{"result": "ok"}'
    url, request = FakeSyncClient.calls[-1]
    assert url == llm_provider.GROQ_URL
    assert request["json"]["response_format"] == {"type": "json_object"}


def test_get_provider_selects_groq(monkeypatch):
    monkeypatch.setattr(llm_provider.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm_provider.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(llm_provider.settings, "groq_model", "test-model")

    provider = llm_provider.get_provider()

    assert isinstance(provider, llm_provider.GroqProvider)
    assert provider.model == "test-model"


def test_get_provider_rejects_missing_groq_key(monkeypatch):
    monkeypatch.setattr(llm_provider.settings, "llm_provider", "groq")
    monkeypatch.setattr(llm_provider.settings, "groq_api_key", "")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm_provider.get_provider()


def test_production_settings_reject_default_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            _env_file=None,
            environment="production",
            llm_provider="groq",
            groq_api_key="test-key",
            jwt_secret="dev-only-secret-change-me",
        )


def test_production_settings_require_groq_key():
    with pytest.raises(ValidationError, match="GROQ_API_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            llm_provider="groq",
            groq_api_key="",
            jwt_secret="a" * 48,
        )


def test_production_settings_accept_valid_groq_configuration():
    config = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://user:password@localhost/test",
        cors_origins="https://warik-ai.pages.dev",
        llm_provider="groq",
        groq_api_key="test-key",
        jwt_secret="a" * 48,
    )

    assert config.llm_provider == "groq"
    assert config.database_url.startswith("postgresql")
    assert config.cors_origin_list == ["https://warik-ai.pages.dev"]


def test_production_settings_reject_sqlite():
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="sqlite:///./warik.db",
            cors_origins="https://warik-ai.pages.dev",
            llm_provider="groq",
            groq_api_key="test-key",
            jwt_secret="a" * 48,
        )


def test_production_settings_reject_wildcard_cors():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://user:password@localhost/test",
            cors_origins="*",
            llm_provider="groq",
            groq_api_key="test-key",
            jwt_secret="a" * 48,
        )


def test_production_settings_reject_http_cors():
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://user:password@localhost/test",
            cors_origins="http://warik-ai.pages.dev",
            llm_provider="groq",
            groq_api_key="test-key",
            jwt_secret="a" * 48,
        )
