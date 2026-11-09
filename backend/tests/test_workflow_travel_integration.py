from unittest.mock import MagicMock

from app.agents.workflow_engine import WorkflowEngine
from app.tools.trip_summary_tool import (
    CompileTripSummaryInput,
    CompileTripSummaryTool,
)


def make_workflow():
    workflow = MagicMock()
    workflow.id = 1
    workflow.goal_id = 1
    workflow.status = "PLANNED"

    workflow.steps_json = [
        {
            "id": "itinerary",
            "tool": "generate_advanced_itinerary",
            "params": {},
            "depends_on": [],
            "status": "PENDING",
            "required": True,
            "dep_policy": "all_success",
            "max_retries": 0,
        },
        {
            "id": "flight",
            "tool": "search_flights_real",
            "params": {},
            "depends_on": [],
            "status": "PENDING",
            "required": False,
            "dep_policy": "tolerate_failure",
            "max_retries": 0,
        },
        {
            "id": "cab",
            "tool": "get_cab_links",
            "params": {},
            "depends_on": [],
            "status": "PENDING",
            "required": False,
            "dep_policy": "tolerate_failure",
            "max_retries": 0,
        },
        {
            "id": "summary",
            "tool": "compile_trip_summary",
            "params": {"destination": "Kochi, Munnar, Alleppey"},
            "depends_on": ["itinerary", "flight", "cab"],
            "status": "PENDING",
            "required": True,
            "dep_policy": "tolerate_failure",
            "max_retries": 0,
        },
    ]

    return workflow


def test_travel_workflow_passes_all_results_to_summary():
    db = MagicMock()
    db.get.return_value = None

    user = MagicMock()
    user.id = 1

    engine = WorkflowEngine(db, user)
    workflow = make_workflow()

    hotel = {
        "name": "Kochi Test Hotel",
        "city": "Kochi",
        "check_in": "2026-12-10",
        "check_out": "2026-12-12",
        "price": "₹5,000",
        "booking_url": "https://example.com/kochi",
    }

    itinerary_data = {
        "type": "advanced_itinerary",
        "destination": "Kochi → Munnar → Alleppey",
        "hotels": [hotel],
        "days": [],
        "notes": [],
    }

    cab_data = {
        "links": {
            "uber": "https://example.com/uber",
            "ola": "https://example.com/ola",
        }
    }

    summary_params_received = {}

    def mock_invoke(step, params):
        tool = step["tool"]

        if tool == "generate_advanced_itinerary":
            return {
                "success": True,
                "error": None,
                "data": itinerary_data,
            }

        if tool == "search_flights_real":
            return {
                "success": False,
                "error": "Flight provider unavailable.",
                "data": None,
            }

        if tool == "get_cab_links":
            return {
                "success": True,
                "error": None,
                "data": cab_data,
            }

        if tool == "compile_trip_summary":
            summary_params_received.update(params)

            summary_result = CompileTripSummaryTool().execute(
                None,
                CompileTripSummaryInput(**params),
            )

            return {
                "success": summary_result.success,
                "error": (
                    None if summary_result.success
                    else summary_result.message
                ),
                "data": summary_result.data,
            }

        raise AssertionError(f"Unexpected tool: {tool}")

    engine._invoke_tool = mock_invoke

    result = engine.execute(workflow)

    # Every discovery step and the summary must execute.
    assert result["executed"] == [
        "itinerary",
        "flight",
        "cab",
        "summary",
    ]

    # The optional flight failure must not block the summary.
    assert result["workflow_status"] == "PARTIALLY_COMPLETED"

    # Verify successful results reached the summary.
    dependencies = summary_params_received["dependency_results"]

    assert dependencies["itinerary"]["result"]["hotels"] == [hotel]
    assert dependencies["cab"]["result"] == cab_data

    # Verify failed flight search reached dependency_failures.
    failures = summary_params_received["dependency_failures"]

    assert failures["flight"]["tool"] == "search_flights_real"
    assert failures["flight"]["error"] == "Flight provider unavailable."

    # Verify the final summary retained the embedded hotel.
    summary_step = next(
        step for step in workflow.steps_json
        if step["id"] == "summary"
    )

    assert summary_step["status"] == "COMPLETED"
    assert summary_step["result"]["hotels"] == [hotel]

    # Verify cab links survived summary compilation.
    assert summary_step["result"]["cabs"] == cab_data["links"]

    # Verify flight failure was reported.
    assert summary_step["result"]["failures"] == [
        {
            "tool": "search_flights_real",
            "error": "Flight provider unavailable.",
        }
    ]


def test_summary_waits_for_all_discovery_steps():
    db = MagicMock()
    db.get.return_value = None

    user = MagicMock()
    workflow = make_workflow()

    engine = WorkflowEngine(db, user)

    # Simulate discovery steps already completed or failed.
    workflow.steps_json[0]["status"] = "COMPLETED"
    workflow.steps_json[1]["status"] = "FAILED"
    workflow.steps_json[2]["status"] = "PENDING"

    calls = []

    def mock_invoke(step, params):
        calls.append(step["id"])
        return {
            "success": True,
            "error": None,
            "data": {},
        }

    engine._invoke_tool = mock_invoke

    result = engine.execute(workflow)

    # Cab executes first; summary executes only after cab is terminal.
    assert calls == ["cab", "summary"]
    assert result["workflow_status"] == "PARTIALLY_COMPLETED"
