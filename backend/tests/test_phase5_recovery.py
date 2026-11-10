from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agents.workflow_engine import WorkflowEngine


def _engine_workflow(step):
    db = MagicMock()
    db.get.return_value = None
    user = MagicMock()
    user.id = 7
    engine = WorkflowEngine(db, user)
    workflow = MagicMock()
    workflow.id = 91
    workflow.goal_id = 91
    workflow.status = "IN_PROGRESS"
    workflow.steps_json = [step]
    return engine, workflow, db


def test_stale_executing_step_is_quarantined_not_replayed():
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    engine, workflow, db = _engine_workflow({
        "id": "create-expense",
        "tool": "add_expense",
        "params": {"amount": 100},
        "depends_on": [],
        "status": "EXECUTING",
        "started_at": old,
        "execution_id": "attempt-1",
        "required": True,
    })

    with patch.object(engine, "_invoke_tool") as invoke:
        result = engine.execute(workflow)

    assert workflow.steps_json[0]["status"] == "RECONCILIATION_REQUIRED"
    assert result["reconciliation_required_steps"] == ["create-expense"]
    assert result["workflow_status"] == "PARTIALLY_COMPLETED"
    invoke.assert_not_called()
    assert any(
        call.args[0].action == "workflow.execution.interrupted"
        for call in db.add.call_args_list
    )


def test_recent_executing_step_is_not_mistaken_for_crash():
    recent = datetime.now(timezone.utc).isoformat()
    engine, workflow, _ = _engine_workflow({
        "id": "long-search",
        "tool": "search",
        "params": {},
        "depends_on": [],
        "status": "EXECUTING",
        "started_at": recent,
        "execution_id": "attempt-live",
        "required": True,
    })

    with patch.object(engine, "_invoke_tool") as invoke:
        result = engine.execute(workflow)

    assert workflow.steps_json[0]["status"] == "EXECUTING"
    assert result["workflow_status"] == "IN_PROGRESS"
    assert result["reconciliation_required_steps"] == []
    invoke.assert_not_called()


def test_completed_step_is_not_reexecuted_on_resume():
    engine, workflow, _ = _engine_workflow({
        "id": "create-task",
        "tool": "create_task",
        "params": {"title": "Already created"},
        "depends_on": [],
        "status": "COMPLETED",
        "result": {"id": 55},
        "execution_id": "attempt-done",
        "required": True,
        "verification": {"status": "VERIFIED"},
    })

    with patch.object(engine, "_invoke_tool") as invoke:
        result = engine.execute(workflow)

    assert result["workflow_status"] == "COMPLETED"
    assert result["executed"] == []
    invoke.assert_not_called()


def test_uncertain_mutating_failure_requires_reconciliation_before_retry():
    engine, workflow, _ = _engine_workflow({
        "id": "mutate",
        "tool": "mutating_tool",
        "params": {},
        "depends_on": [],
        "status": "APPROVED",
        "approval_required": True,
        "approval_granted": True,
        "required": True,
        "max_retries": 2,
        "retry_count": 0,
    })
    mutating_tool = SimpleNamespace(
        is_mutating=True,
        requires_confirmation=False,
    )

    with patch("app.agents.workflow_engine.registry.get", return_value=mutating_tool), \
         patch.object(engine, "_invoke_tool", return_value={
             "success": False,
             "error": "connection lost after request",
             "data": None,
         }):
        result = engine.execute(workflow)

    step = workflow.steps_json[0]
    assert step["status"] == "RECONCILIATION_REQUIRED"
    assert result["reconciliation_required_steps"] == ["mutate"]
    retry = engine.retry_step(workflow, "mutate")
    assert retry["ok"] is False
    assert "reconcile" in retry["reason"].lower()
