import asyncio
import json

import pytest

from app.agents.goal_interpreter import (
    GoalInterpreter,
    TravelClarificationRequired,
)


def _travel_steps(check_in=None, check_out=None):
    params = {
        "destination": "Jaipur",
        "days": 3,
        "include_hotels": True,
    }

    if check_in is not None:
        params["check_in"] = check_in

    if check_out is not None:
        params["check_out"] = check_out

    return [
        {
            "id": "itinerary",
            "description": "Generate itinerary and hotels",
            "tool": "generate_advanced_itinerary",
            "params": params,
            "depends_on": [],
        }
    ]


def test_hotel_request_without_dates_requires_clarification():
    with pytest.raises(TravelClarificationRequired, match="check-in and check-out"):
        GoalInterpreter._normalize_travel_steps(
            _travel_steps(),
            {"destination": "Jaipur"},
        )


def test_hotel_request_with_invalid_date_order_requires_clarification():
    with pytest.raises(TravelClarificationRequired, match="must be after"):
        GoalInterpreter._normalize_travel_steps(
            _travel_steps("2026-12-15", "2026-12-10"),
            {"destination": "Jaipur"},
        )


def test_interpreter_returns_clarification_instead_of_dropping_hotels():
    class FakeProvider:
        async def _call(self, *args, **kwargs):
            return json.dumps(
                {
                    "goal_title": "Jaipur trip",
                    "goal_description": "Plan a Jaipur trip with hotels",
                    "context": {"destination": "Jaipur"},
                    "steps": _travel_steps(),
                }
            )

    interpreter = GoalInterpreter.__new__(GoalInterpreter)
    interpreter.provider = FakeProvider()

    result = asyncio.run(
        interpreter.interpret("Plan a 3-day Jaipur trip with hotels")
    )

    assert result["plan"] is None
    assert result["needs_clarification"] is True
    assert "check-in and check-out" in result["clarification_question"]
