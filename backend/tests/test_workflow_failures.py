"""Tests for failure-isolated workflow execution."""
import pytest
from unittest.mock import MagicMock, patch
from app.agents.workflow_engine import WorkflowEngine
from app.schemas.workflow import WorkflowPlan, WorkflowStep


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

    # Manually construct a workflow object
    wf = MagicMock()
    wf.id = 1
    wf.goal_id = 1
    wf.status = "PLANNED"
    wf.steps_json = [
        {"id": "flight", "tool": "search_flights_real", "params": {}, "depends_on": [],
         "status": "PENDING", "required": False, "dep_policy": "all_success", "max_retries": 0},
        {"id": "hotel", "tool": "search_hotels_stayapi", "params": {}, "depends_on": [],
         "status": "PENDING", "required": False, "dep_policy": "all_success", "max_retries": 0},
        {"id": "cab", "tool": "get_cab_links", "params": {}, "depends_on": [],
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
    """Server-side tool policy overrides a planner's approval_required=false."""
    from types import SimpleNamespace
    from app.agents import workflow_engine as workflow_module

    engine = WorkflowEngine(mock_db, mock_user)
    wf = MagicMock()
    wf.id = 11
    wf.goal_id = 11
    wf.steps_json = [
        {
            "id": "sensitive",
            "tool": "sensitive_test_tool",
            "description": "Record a sensitive change",
            "params": {},
            "depends_on": [],
            "status": "PENDING",
            "required": True,
            "approval_required": False,
            "dep_policy": "all_success",
            "max_retries": 0,
        }
    ]
    fake_tool = SimpleNamespace(
        requires_confirmation=True,
        is_mutating=False,
        input_schema=lambda **params: object(),
        confirmation_prompt=lambda params: "record the sensitive change",
    )

    with patch.object(workflow_module.registry, "get", return_value=fake_tool), \
         patch.object(engine, "_invoke_tool") as invoke:
        result = engine.execute(wf)

    assert result["workflow_status"] == "AWAITING_APPROVAL"
    assert result["awaiting_approval"]["approval_required"] is True
    assert result["awaiting_approval"]["approval_prompt"] == "record the sensitive change"
    invoke.assert_not_called()
