"""Tests for failure-isolated workflow execution."""
import pytest
from unittest.mock import MagicMock, patch
from app.agents.workflow_engine import WorkflowEngine
from app.schemas.workflow import WorkflowPlan, WorkflowStep
from .schema_fixtures import find_schema_tool, valid_required_tool_params


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.get = MagicMock(return_value=None)
    return db


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    return user


def _plan_with_steps(steps):
    return WorkflowPlan(
        goal_title="Test",
        goal_description="",
        context={},
        steps=steps,
    )


def test_independent_steps_continue_after_failure(mock_db, mock_user):
    """Flight fails, hotel + cab still execute."""
    engine = WorkflowEngine(mock_db, mock_user)
    engine._select_step_provider = lambda *_args, **_kwargs: (None, None)

    # Manually construct a workflow object
    wf = MagicMock()
    wf.id = 1
    wf.goal_id = 1
    wf.status = "PLANNED"
    wf.steps_json = [
        {"id": "flight", "tool": "search_flights_real", "params": valid_required_tool_params("search_flights_real"), "depends_on": [],
         "status": "PENDING", "required": False, "dep_policy": "all_success", "max_retries": 0},
        {"id": "hotel", "tool": "search_hotels_stayapi", "params": valid_required_tool_params("search_hotels_stayapi"), "depends_on": [],
         "status": "PENDING", "required": False, "dep_policy": "all_success", "max_retries": 0},
        {"id": "cab", "tool": "get_cab_links", "params": valid_required_tool_params("get_cab_links"), "depends_on": [],
         "status": "PENDING", "required": False, "dep_policy": "all_success", "max_retries": 0},
        {"id": "compile", "tool": "compile_trip_summary", "params": {},
         "depends_on": ["flight", "hotel", "cab"],
         "status": "PENDING", "required": True, "dep_policy": "tolerate_failure", "max_retries": 0},
    ]

    def mock_invoke(step, params):
       if step["tool"] == "search_flights_real":
         return {
            "success": False,
            "error": "unavailable",
            "data": None,
        }

       return {
        "success": True,
        "error": None,
        "data": {},
    }

    with patch.object(engine, '_invoke_tool', side_effect=mock_invoke):
        result = engine.execute(wf)

    # All steps ran
    assert "flight" in result["executed"]
    assert "hotel" in result["executed"]
    assert "cab" in result["executed"]
    assert "compile" in result["executed"]

    # Overall status
    assert result["workflow_status"] == "PARTIALLY_COMPLETED"


def test_all_required_fail_marks_failed(mock_db, mock_user):
    engine = WorkflowEngine(mock_db, mock_user)
    wf = MagicMock()
    wf.id = 1
    wf.goal_id = 1
    wf.steps_json = [
        {"id": "a", "tool": "x", "params": {}, "depends_on": [],
         "status": "PENDING", "required": True, "dep_policy": "all_success", "max_retries": 0},
    ]

    with patch.object(engine, '_invoke_tool', return_value={"success": False, "error": "boom", "data": None}):
        result = engine.execute(wf)

    assert result["workflow_status"] == "FAILED"


def test_all_success_marks_completed(mock_db, mock_user):
    engine = WorkflowEngine(mock_db, mock_user)
    wf = MagicMock()
    wf.id = 1
    wf.goal_id = 1
    wf.steps_json = [
        {"id": "a", "tool": "x", "params": {}, "depends_on": [],
         "status": "PENDING", "required": True, "dep_policy": "all_success", "max_retries": 0},
    ]

    with patch.object(engine, '_invoke_tool', return_value={"success": True, "error": None, "data": {}}):
        result = engine.execute(wf)

    assert result["workflow_status"] == "COMPLETED"

def test_approved_step_executes_after_confirmation(mock_db, mock_user):
    """An approved step must be picked up by execute(), not left stranded."""
    engine = WorkflowEngine(mock_db, mock_user)
    wf = MagicMock()
    wf.id = 10
    wf.goal_id = 10
    wf.steps_json = [
        {
            "id": "mutating",
            "tool": "sensitive_test_tool",
            "description": "Perform a sensitive action",
            "params": {},
            "depends_on": [],
            "status": "PENDING",
            "required": True,
            "approval_required": True,
            "dep_policy": "all_success",
            "max_retries": 0,
        }
    ]

    with patch.object(
        engine,
        "_invoke_tool",
        return_value={"success": True, "error": None, "data": {"done": True}},
    ) as invoke:
        first = engine.execute(wf)
        assert first["workflow_status"] == "AWAITING_APPROVAL"
        assert first["awaiting_approval"]["id"] == "mutating"
        invoke.assert_not_called()

        assert engine.approve_step(wf, "mutating") is True
        second = engine.execute(wf)

    assert second["executed"] == ["mutating"]
    assert second["workflow_status"] == "COMPLETED"
    invoke.assert_called_once()


def test_tool_metadata_forces_workflow_approval(mock_db, mock_user):
    """Server-side mutability metadata forces approval."""
    from types import SimpleNamespace
    from app.agents import workflow_engine as workflow_module

    schema_tool = find_schema_tool()
    fake_tool = SimpleNamespace(
        name="fixture_mutating_tool",
        requires_confirmation=True,
        is_mutating=False,
        provider_adapters=(),
        input_schema=schema_tool.input_schema,
        confirmation_prompt=lambda params: "Confirm the test action",
    )

    engine = WorkflowEngine(mock_db, mock_user)
    engine._select_step_provider = lambda *_args, **_kwargs: (None, None)

    wf = MagicMock()
    wf.id = 11
    wf.goal_id = 11
    wf.steps_json = [{
        "id": "sensitive",
        "tool": fake_tool.name,
        "description": "Test approval policy",
        "params": valid_required_tool_params(schema_tool),
        "depends_on": [],
        "status": "PENDING",
        "required": True,
        "approval_required": False,
        "dep_policy": "all_success",
        "max_retries": 0,
    }]

    with patch.object(workflow_module.registry, "get", return_value=fake_tool):
        with patch.object(engine, "_invoke_tool") as invoke:
            result = engine.execute(wf)

    assert result["workflow_status"] == "AWAITING_APPROVAL"
    assert result["awaiting_approval"]["approval_required"] is True
    assert result["awaiting_approval"]["approval_prompt"] == "Confirm the test action"
    invoke.assert_not_called()
