from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from app.agents.workflow_engine import WorkflowEngine
from app.tools.base import BaseTool

import pytest


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.get = MagicMock(return_value=None)
    return db


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    return user


class EmptyInput(BaseModel):
    pass


class VerifiableTool(BaseTool):
    name = "verifiable_test_tool"
    input_schema = EmptyInput

    def execute(self, ctx, params):  # pragma: no cover - execution is mocked
        raise NotImplementedError

    def verify(self, ctx, params, result):
        return {
            "verified": True,
            "method": "test_readback",
            "evidence": {"record_id": 42},
        }


class UnverifiableTool(BaseTool):
    name = "unverifiable_test_tool"
    input_schema = EmptyInput

    def execute(self, ctx, params):  # pragma: no cover - execution is mocked
        raise NotImplementedError


class FailedVerificationTool(VerifiableTool):
    name = "failed_verification_test_tool"

    def verify(self, ctx, params, result):
        return {"verified": False, "method": "test_readback", "evidence": {"found": False}}


def _run(tool, mock_db, mock_user):
    engine = WorkflowEngine(mock_db, mock_user)
    workflow = MagicMock()
    workflow.id = 7
    workflow.goal_id = 3
    workflow.status = "PLANNED"
    workflow.steps_json = [{
        "id": "step-1", "tool": tool.name, "params": {}, "depends_on": [],
        "status": "PENDING", "required": True, "max_retries": 0,
    }]
    with patch("app.agents.workflow_engine.registry.get", return_value=tool), patch.object(
        engine, "_invoke_tool", return_value={"success": True, "error": None, "data": {"ok": True}}
    ):
        result = engine.execute(workflow)
    return workflow, result


def test_successful_execution_is_independently_verified(mock_db, mock_user):
    workflow, result = _run(VerifiableTool(), mock_db, mock_user)
    step = workflow.steps_json[0]
    assert step["status"] == "COMPLETED"
    assert step["verification"]["status"] == "VERIFIED"
    assert step["verification"]["evidence"] == {"record_id": 42}
    assert result["verified_steps"] == ["step-1"]
    assert result["workflow_status"] == "COMPLETED"


def test_missing_verifier_is_reported_as_unverified_not_verified(mock_db, mock_user):
    workflow, result = _run(UnverifiableTool(), mock_db, mock_user)
    assert workflow.steps_json[0]["status"] == "COMPLETED"
    assert workflow.steps_json[0]["verification"]["status"] == "UNVERIFIED"
    assert result["unverified_steps"] == ["step-1"]
    assert result["workflow_status"] == "COMPLETED"


def test_failed_verification_marks_workflow_partial_without_retrying_side_effect(mock_db, mock_user):
    workflow, result = _run(FailedVerificationTool(), mock_db, mock_user)
    step = workflow.steps_json[0]
    assert step["status"] == "COMPLETED"
    assert step["verification"]["status"] == "FAILED"
    assert result["verification_failures"][0]["step_id"] == "step-1"
    assert result["workflow_status"] == "PARTIALLY_COMPLETED"
    assert step.get("retry_count", 0) == 0
