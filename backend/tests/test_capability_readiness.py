
from types import SimpleNamespace

from app.api.health import build_capability_status


def make_config(**overrides):
    values = {
        "llm_provider": "groq",
        "groq_api_key": "",
        "ollama_model": "llama3.2:latest",
        "duffel_api_key": "",
        "booking_mode": "disabled",
        "booking_api_token": "",
        "booking_affiliate_id": "",
        "voice_enabled": False,
        "gnani_api_key": "",
        "swiggy_mode": "mock",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def by_id(result):
    return {service["id"]: service for service in result["services"]}


def test_capability_status_marks_unconfigured_integrations_without_cli():
    result = build_capability_status(make_config(), cli_available=False)
    services = by_id(result)

    assert services["assistant"]["status"] == "missing_credentials"
    assert services["flights"]["status"] == "external_search_only"
    assert services["hotels"]["status"] == "external_search_only"
    assert services["rides"]["status"] == "handoff_only"
    assert services["rail_bus"]["status"] == "handoff_only"
    assert services["voice"]["status"] == "disabled"
    assert services["food"]["status"] == "mock"
    assert services["places"]["status"] == "best_effort"


def test_capability_status_reports_configured_provider_paths_without_secrets():
    config = make_config(
        groq_api_key="groq-secret-value",
        duffel_api_key="duffel-secret-value",
        booking_mode="search_and_redirect",
        booking_api_token="booking-secret-value",
        booking_affiliate_id="affiliate-secret-value",
        voice_enabled=True,
        gnani_api_key="gnani-secret-value",
        swiggy_mode="live",
    )

    result = build_capability_status(config, cli_available=False)
    services = by_id(result)

    assert services["assistant"]["status"] == "configured"
    assert services["flights"]["status"] == "configured"
    assert services["hotels"]["status"] == "configured"
    assert services["voice"]["status"] == "configured"
    assert services["food"]["status"] == "account_connection"

    serialized = str(result)
    for secret in (
        "groq-secret-value",
        "duffel-secret-value",
        "booking-secret-value",
        "affiliate-secret-value",
        "gnani-secret-value",
    ):
        assert secret not in serialized


def test_capability_status_reports_legacy_cli_as_fallback():
    result = build_capability_status(make_config(), cli_available=True)
    services = by_id(result)

    assert services["flights"]["status"] == "legacy_provider"
    assert services["hotels"]["status"] == "legacy_provider"


def test_capability_status_does_not_call_itself_a_live_health_check():
    result = build_capability_status(make_config(), cli_available=False)
    assert "not a live availability test" in result["note"]
