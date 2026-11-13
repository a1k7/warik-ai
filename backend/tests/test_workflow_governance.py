from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import update
from sqlalchemy.dialects import postgresql

from app.models import Goal, User, Workflow
from app.agents.workflow_engine import (
    WorkflowEngine,
    _workflow_steps_match_condition,
)


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


def test_rejected_step_cannot_be_retried(engine_and_workflow):
    engine, workflow, _ = engine_and_workflow

    assert engine.reject_step(workflow, "sensitive", "Not authorized")

    result = engine.retry_step(workflow, "sensitive")

    assert result["ok"] is False
    assert "not FAILED" in result["reason"]
    assert workflow.steps_json[0]["status"] == "REJECTED"


def test_required_rejection_produces_rejected_workflow(engine_and_workflow):
    engine, _, _ = engine_and_workflow

    steps = [
        {
            "id": "required",
            "status": "REJECTED",
            "required": True,
        }
    ]

    assert engine._compute_overall_status(steps, None) == "REJECTED"


def test_optional_rejection_allows_partial_completion(engine_and_workflow):
    engine, _, _ = engine_and_workflow

    steps = [
        {
            "id": "required",
            "status": "COMPLETED",
            "required": True,
        },
        {
            "id": "optional",
            "status": "REJECTED",
            "required": False,
        },
    ]

    assert (
        engine._compute_overall_status(steps, None)
        == "PARTIALLY_COMPLETED"
    )


@pytest.mark.parametrize("operation", ["approve", "reject", "retry"])
def test_transition_refuses_to_overwrite_concurrent_workflow_change(
    engine_and_workflow, operation
):
    engine, workflow, db = engine_and_workflow
    if operation == "retry":
        workflow.steps_json[0]["status"] = "FAILED"

    engine._compare_and_swap_steps = MagicMock(return_value=False)
    before = engine._steps(workflow)

    if operation == "approve":
        result = engine.approve_step(workflow, "sensitive")
        assert result is False
    elif operation == "reject":
        result = engine.reject_step(workflow, "sensitive", "Not authorized")
        assert result is False
    else:
        result = engine.retry_step(workflow, "sensitive")
        assert result["ok"] is False
        assert "concurrently" in result["reason"]

    assert workflow.steps_json == before
    db.add.assert_not_called()


def test_approve_step_writes_audit_event(engine_and_workflow):
    engine, workflow, db = engine_and_workflow

    assert engine.approve_step(workflow, "sensitive") is True

    audit_actions = [
        call.args[0].action
        for call in db.add.call_args_list
        if call.args
    ]
    assert "workflow.step.approved" in audit_actions


def test_retry_step_writes_audit_event():
    db = MagicMock()
    user = MagicMock()
    user.id = 7
    engine = WorkflowEngine(db, user)
    workflow = MagicMock()
    workflow.id = 44
    workflow.steps_json = [{
        "id": "unstable",
        "tool": "unstable_tool",
        "params": {},
        "depends_on": [],
        "status": "FAILED",
        "retry_count": 0,
        "max_retries": 1,
    }]

    result = engine.retry_step(workflow, "unstable")

    assert result == {"ok": True, "retry_count": 1}
    audit_actions = [
        call.args[0].action
        for call in db.add.call_args_list
        if call.args
    ]
    assert "workflow.step.retried" in audit_actions

def test_postgresql_cas_uses_jsonb_equality():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"

    old_steps = [{"id": "step-1", "status": "PENDING"}]
    condition = _workflow_steps_match_condition(session, old_steps)
    statement = update(Workflow).where(condition)

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "CAST(workflows.steps_json AS JSONB)" in sql
    assert sql.count("JSONB") >= 2
    assert any(value == old_steps for value in compiled.params.values())


def test_sqlite_cas_keeps_native_json_comparison():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "sqlite"

    old_steps = [{"id": "step-1", "status": "PENDING"}]
    condition = _workflow_steps_match_condition(session, old_steps)
    statement = update(Workflow).where(condition)

    sql = str(statement.compile())

    assert "CAST(" not in sql
    assert "workflows.steps_json =" in sql


def test_sqlite_compare_and_swap_rejects_stale_workflow_state(db_session):
    user = User(
        email="cas-integration@example.test",
        name="CAS Integration",
        password_hash="not-a-real-password-hash",
    )
    db_session.add(user)
    db_session.flush()

    goal = Goal(
        user_id=user.id,
        title="CAS integration test",
        status="PLANNED",
    )
    db_session.add(goal)
    db_session.flush()

    original_steps = [
        {
            "id": "step-1",
            "tool": "example_tool",
            "params": {},
            "depends_on": [],
            "status": "PENDING",
            "required": True,
        }
    ]
    workflow = Workflow(
        user_id=user.id,
        goal_id=goal.id,
        status="IN_PROGRESS",
        steps_json=original_steps,
    )
    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)

    engine = WorkflowEngine(db_session, user)
    stale_snapshot = [dict(step) for step in original_steps]

    concurrent_steps = [
        {
            **original_steps[0],
            "status": "COMPLETED",
            "result": {"writer": "concurrent-update"},
        }
    ]
    proposed_steps = [
        {
            **original_steps[0],
            "status": "APPROVED",
            "approval_granted": True,
        }
    ]

    # Simulate another writer committing after the workflow was read.
    db_session.query(Workflow).filter(
        Workflow.id == workflow.id
    ).update(
        {Workflow.steps_json: concurrent_steps},
        synchronize_session=False,
    )
    db_session.commit()

    updated = engine._compare_and_swap_steps(
        workflow,
        stale_snapshot,
        proposed_steps,
    )

    assert updated is False
    assert workflow.steps_json == concurrent_steps

    persisted = (
        db_session.query(Workflow)
        .filter(Workflow.id == workflow.id)
        .one()
    )
    assert persisted.steps_json == concurrent_steps
    assert persisted.steps_json != proposed_steps
