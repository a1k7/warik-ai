from unittest.mock import MagicMock, patch

import pytest

from app.agents.workflow_engine import WorkflowEngine


@pytest.fixture
def engine_and_workflow():
    db = MagicMock()
    user = MagicMock()
    user.id = 7
    engine = WorkflowEngine(db, user)
    workflow = MagicMock()
    workflow.id = 41
    workflow.goal_id = 41
    workflow.status = "AWAITING_APPROVAL"
    workflow.steps_json = [
        {
            "id": "sensitive",
            "tool": "sensitive_test_tool",
            "description": "Sensitive operation",
            "params": {},
            "depends_on": [],
            "status": "AWAITING_APPROVAL",
            "required": True,
            "approval_required": True,
            "dep_policy": "all_success",
            "retry_count": 0,
            "max_retries": 1,
        }
    ]
    return engine, workflow, db


def test_reject_step_persists_rejected_and_never_invokes_tool(engine_and_workflow):
    engine, workflow, db = engine_and_workflow
    with patch.object(engine, "_invoke_tool") as invoke:
        assert engine.reject_step(workflow, "sensitive", "Not authorized")
        result = engine.execute(workflow)

    step = workflow.steps_json[0]
    assert step["status"] == "REJECTED"
    assert step["error"] == "Not authorized"
    assert result["executed"] == []
    invoke.assert_not_called()
    assert any(
        call.args[0].action == "workflow.step.rejected"
        for call in db.add.call_args_list
    )


def test_approve_only_accepts_awaiting_approval(engine_and_workflow):
    engine, workflow, _ = engine_and_workflow
    assert engine.approve_step(workflow, "sensitive") is True
    assert workflow.steps_json[0]["status"] == "APPROVED"
    assert engine.approve_step(workflow, "sensitive") is False


def test_retry_limit_means_retries_after_initial_attempt():
    db = MagicMock()
    user = MagicMock()
    user.id = 7
    engine = WorkflowEngine(db, user)
    workflow = MagicMock()
    workflow.id = 42
    workflow.status = "FAILED"
    workflow.steps_json = [
        {
            "id": "unstable",
            "tool": "unstable_tool",
            "params": {},
            "depends_on": [],
            "status": "FAILED",
            "required": True,
            "retry_count": 0,
            "max_retries": 1,
        }
    ]

    first = engine.retry_step(workflow, "unstable")
    assert first == {"ok": True, "retry_count": 1}
    workflow.steps_json[0]["status"] = "FAILED"

    second = engine.retry_step(workflow, "unstable")
    assert second["ok"] is False
    assert second["reason"] == "Max retries exceeded"


def test_zero_retries_disallows_retry():
    db = MagicMock()
    user = MagicMock()
    user.id = 7
    engine = WorkflowEngine(db, user)
    workflow = MagicMock()
    workflow.id = 43
    workflow.steps_json = [
        {
            "id": "no-retry",
            "tool": "tool",
            "params": {},
            "depends_on": [],
            "status": "FAILED",
            "retry_count": 0,
            "max_retries": 0,
        }
    ]
    result = engine.retry_step(workflow, "no-retry")
    assert result == {"ok": False, "reason": "Max retries exceeded"}
