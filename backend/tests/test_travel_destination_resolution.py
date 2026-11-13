from types import SimpleNamespace

from app.agents.orchestrator import _resolve_itinerary_destination


def test_goa_budget_inclusions_do_not_overwrite_destination():
    plan = SimpleNamespace(
        context={"destination": "Goa"},
        steps=[],
    )

    result = _resolve_itinerary_destination(
        plan,
        "Plan a four-day Goa trip within ₹20,000, including transport and food.",
    )

    assert result == "Goa"
    assert plan.context["destination"] == "Goa"


def test_preserves_multi_city_destination():
    destination = "Kochi, Munnar, Alleppey"

    plan = SimpleNamespace(
        context={"destination": destination},
        steps=[],
    )

    result = _resolve_itinerary_destination(
        plan,
        "Plan a four-day trip covering Kochi, Munnar and Alleppey.",
    )

    assert result == destination


def test_falls_back_to_itinerary_step_destination():
    step = SimpleNamespace(
        tool="generate_advanced_itinerary",
        params={"destination": "Jaipur"},
    )

    plan = SimpleNamespace(
        context={},
        steps=[step],
    )

    result = _resolve_itinerary_destination(
        plan,
        "Plan a four-day trip within ₹20,000, including food.",
    )

    assert result == "Jaipur"
    assert plan.context["destination"] == "Jaipur"


def test_missing_destination_does_not_invent_a_place():
    plan = SimpleNamespace(
        context={},
        steps=[],
    )

    result = _resolve_itinerary_destination(
        plan,
        "Plan a four-day trip within ₹20,000, including transport and food.",
    )

    assert result is None
