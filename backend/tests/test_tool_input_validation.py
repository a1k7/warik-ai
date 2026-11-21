"""Regression tests for shared tool-input validation."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.agents.workflow_engine import WorkflowEngine
from app.tools.input_validation import validate_tool_input
from app.tools.registry import ToolRegistry


class RequiredOrigin(BaseModel):
    origin: str


class FakeTool:
    name = "test_required_origin"
    input_schema = RequiredOrigin

    def __init__(self):
        self.calls = 0

    def execute(self, ctx, params):
        self.calls += 1
        raise AssertionError("Invalid tool input must never execute")


@pytest.mark.parametrize(
    "value",
    ["empty", " UNKNOWN ", "TBD", "not provided", "<origin>", "[origin]"],
)
def test_registry_dispatch_rejects_required_string_placeholders(value):
    tool = FakeTool()
    local_registry = ToolRegistry.__new__(ToolRegistry)
    local_registry._tools = {tool.name: tool}

    result = local_registry.dispatch(
        SimpleNamespace(db=None),
        tool.name,
        {"origin": value},
    )

    assert result.success is False
    assert "placeholder" in result.message.lower()
    assert tool.calls == 0


def test_binding_resolved_placeholder_is_rejected_by_runtime_validator():
    engine = WorkflowEngine.__new__(WorkflowEngine)
    tool = FakeTool()

    source_step = {
        "id": "source",
        "status": "COMPLETED",
        "result": {"origin": "empty"},
    }
    target_step = {
        "id": "target",
        "tool": tool.name,
        "depends_on": ["source"],
        "params": {},
        "input_bindings": {
            "origin": {
                "source_step": "source",
                "source_path": "origin",
                "required": True,
            }
        },
    }

    resolved_params = engine._inject_dependency_results(
        target_step,
        [source_step, target_step],
    )

    assert resolved_params["origin"] == "empty"

    with pytest.raises(ValueError, match="placeholder"):
        validate_tool_input(tool, resolved_params)

    assert tool.calls == 0


def test_real_required_string_is_accepted():
    tool = FakeTool()

    result = validate_tool_input(
        tool,
        {"origin": "New Delhi"},
    )

    assert result.origin == "New Delhi"


def test_missing_required_field_remains_a_schema_error():
    tool = FakeTool()

    with pytest.raises(ValueError):
        validate_tool_input(tool, {})
