import asyncio

from app.agents import orchestrator
from app.agents.orchestrator import handle_message
from app.models import User
from app.schemas.workflow import WorkflowPlan, WorkflowStep
from app.core.security import hash_password
from app.tools.base import ToolResult


def _user(db) -> User:
    user = User(
        email="travel-orch@example.com",
        name="Travel Test",
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_travel_request_returns_compiled_summary(
    db_session,
    monkeypatch,
):
    user = _user(db_session)

    plan = WorkflowPlan(
        goal_title="Kerala Trip",
        goal_description="Plan a four-day Kerala trip",
        context={
            "destination": "Kochi, Munnar, Alleppey",
        },
        steps=[
            WorkflowStep(
                id="itinerary",
                description="Generate itinerary and hotels",
                tool="generate_advanced_itinerary",
                params={
                    "destination": "Kochi, Munnar, Alleppey",
                    "days": 4,
                    "include_hotels": True,
                    "check_in": "2026-12-10",
                    "check_out": "2026-12-14",
                },
                required=True,
            ),
            WorkflowStep(
                id="flights",
                description="Search flights",
                tool="search_flights_real",
                params={
                    "origin": "Mumbai",
                    "destination": "Kochi",
                    "date": "2026-12-10",
                },
                required=False,
                dep_policy="tolerate_failure",
            ),
            WorkflowStep(
                id="cab",
                description="Get cab links",
                tool="get_cab_links",
                params={
                    "pickup_location": "Kochi Airport",
                    "dropoff_location": "Kochi",
                },
                required=False,
                dep_policy="tolerate_failure",
            ),
            WorkflowStep(
                id="summary",
                description="Compile trip summary",
                tool="compile_trip_summary",
                params={
                    "destination": "Kochi, Munnar, Alleppey",
                },
                depends_on=["itinerary", "flights", "cab"],
                required=True,
                dep_policy="tolerate_failure",
            ),
        ],
    )

    async def fake_interpret(self, user_message, conversation_context=""):
        return {"plan": plan}

    monkeypatch.setattr(
        orchestrator.GoalInterpreter,
        "interpret",
        fake_interpret,
    )

    monkeypatch.setattr(
        orchestrator,
        "get_provider",
        lambda: object(),
    )

    original_dispatch = orchestrator.registry.dispatch

    def mocked_dispatch(ctx, tool_name, params):
        if tool_name == "generate_advanced_itinerary":
            return ToolResult(
                success=True,
                message="Itinerary generated",
                data={
                    "destination": "Kochi, Munnar, Alleppey",
                    "days": 4,
                    "itinerary": [
                        {"day": 1, "city": "Kochi"},
                        {"day": 2, "city": "Kochi"},
                        {"day": 3, "city": "Munnar"},
                        {"day": 4, "city": "Alleppey"},
                    ],
                    "hotels": [
                        {
                            "name": "Kochi Hotel",
                            "city": "Kochi",
                            "check_in": "2026-12-10",
                            "check_out": "2026-12-12",
                            "booking_url": "https://example.com/kochi",
                        },
                        {
                            "name": "Munnar Hotel",
                            "city": "Munnar",
                            "check_in": "2026-12-12",
                            "check_out": "2026-12-13",
                            "booking_url": "https://example.com/munnar",
                        },
                    ],
                    "notes": [],
                },
            )

        if tool_name == "search_flights_real":
            return ToolResult(
                success=False,
                message="Flight provider temporarily unavailable",
                data={},
            )

        if tool_name == "get_cab_links":
            return ToolResult(
                success=True,
                message="Cab links generated",
                data={
                    "type": "transport_links",
                    "links": {
                        "uber": "https://example.com/uber",
                        "ola": "https://example.com/ola",
                    },
                },
            )

        # Keep the real summary tool and all other registry behavior.
        return original_dispatch(ctx, tool_name, params)

    monkeypatch.setattr(
        orchestrator.registry,
        "dispatch",
        mocked_dispatch,
    )

    response = asyncio.run(
        handle_message(
            db_session,
            user,
            (
                "Plan a 4-day trip covering Kochi, Munnar "
                "and Alleppey from Mumbai"
            ),
        )
    )

    assert response.structured_data is not None

    summary = response.structured_data
    print("\n--- TRAVEL WORKFLOW DIAGNOSTIC ---")
    print("STRUCTURED DATA:", response.structured_data)

    assert summary["type"] == "trip_summary"
    assert summary["destination"] == "Kochi, Munnar, Alleppey"

    # Itinerary and embedded hotel results must survive aggregation.
    assert summary["itinerary"] is not None
    assert len(summary["itinerary"]["itinerary"]) == 4

    assert len(summary["hotels"]) == 2
    assert summary["hotels"][0]["name"] == "Kochi Hotel"
    assert summary["hotels"][1]["name"] == "Munnar Hotel"

    # Cab links must be included.
    assert summary["cabs"]["uber"] == "https://example.com/uber"
    assert summary["cabs"]["ola"] == "https://example.com/ola"

    # Failed optional flight discovery must not erase successful results.
    assert summary["flights"] == []
    assert any(
        failure["tool"] == "search_flights_real"
        and "temporarily unavailable" in failure["error"]
        for failure in summary["failures"]
    )

    # Overall workflow should preserve partial success.
    from app.models import Workflow

    workflow = (
        db_session.query(Workflow)
        .filter(Workflow.user_id == user.id)
        .order_by(Workflow.id.desc())
        .first()
    )

    assert workflow is not None
    assert workflow.status == "PARTIALLY_COMPLETED"
