"""Regression tests for workflow approval checkpoints."""
from unittest.mock import MagicMock, patch

from app.agents.workflow_engine import WorkflowEngine


def test_approved_step_is_executable_after_approval():
    db = MagicMock()
    db.get.return_value = None
    user = MagicMock(id=7)
    engine = WorkflowEngine(db, user)
    workflow = MagicMock()
    workflow.id = 10
    workflow.goal_id = 20
    workflow.status = "PLANNED"
    workflow.steps_json = [{
        "id": "write",
        "description": "Write a change",
        "tool": "create_task",
        "params": {"title": "Approved task"},
        "depends_on": [],
        "status": "PENDING",
        "approval_required": True,
        "required": True,
        "dep_policy": "all_success",
        "max_retries": 0,
    }]

    first = engine.execute(workflow)
    assert first["awaiting_approval"]["id"] == "write"
    assert workflow.steps_json[0]["status"] == "AWAITING_APPROVAL"

    assert engine.approve_step(workflow, "write") is True
    assert workflow.steps_json[0]["approval_granted"] is True
    assert workflow.steps_json[0]["status"] == "APPROVED"

    with patch.object(engine, "_invoke_tool", return_value={"success": True, "error": None, "data": {"id": 1}}), \
         patch.object(engine, "_verify_tool_result", return_value={
             "status": "VERIFIED",
             "method": "test_verifier",
             "message": "Test outcome verified.",
             "evidence": {"test": True},
             "checked_at": "2026-01-01T00:00:00+00:00",
         }):
        second = engine.execute(workflow)

    assert second["executed"] == ["write"]
    assert second["workflow_status"] == "COMPLETED"
