from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.agents.workflow_engine import WorkflowEngine
from app.schemas.workflow import WorkflowInputBinding, WorkflowPlan
from app.agents.universal_planner import UniversalTaskPlanner


class ConsumerInput(BaseModel):
    location: str


class FakeTool:
    name = "consume_location"
    description = "Consume a location"
    capability = "test"
    input_schema = ConsumerInput
    requires_confirmation = False
    is_mutating = False


class FakeRegistry:
    def __init__(self):
        self.tool = FakeTool()

    def get(self, name):
        return self.tool if name == self.tool.name else None

    def dispatch(self, ctx, name, params):
        return SimpleNamespace(success=True, message="ok", data={"used": params["location"]})


def test_workflow_binding_schema_accepts_safe_dot_paths():
    binding = WorkflowInputBinding(
        source_step="hotel_search", source_path="items.0.address"
    )
    assert binding.source_path == "items.0.address"


@pytest.mark.parametrize("path", ["", "items..address", "__class__", "items.0.__dict__", "items[0].name"])
def test_workflow_binding_schema_rejects_unsafe_or_ambiguous_paths(path):
    with pytest.raises(Exception):
        WorkflowInputBinding(source_step="source", source_path=path)


def test_engine_resolves_generic_dependency_binding_and_passes_to_tool():
    db = MagicMock()
    db.get.return_value = None
    engine = WorkflowEngine(db, MagicMock(id=5), tool_registry=FakeRegistry())
    workflow = MagicMock(id=10, goal_id=20, status="PLANNED")
    workflow.steps_json = [
        {
            "id": "hotel_search", "tool": "search_hotels", "params": {},
            "depends_on": [], "status": "COMPLETED",
            "result": {"items": [{"address": "MG Road, Bengaluru"}]},
        },
        {
            "id": "restaurant_search", "tool": "consume_location", "params": {},
            "depends_on": ["hotel_search"], "status": "PENDING",
            "input_bindings": {
                "location": {
                    "source_step": "hotel_search",
                    "source_path": "items.0.address",
                    "required": True,
                }
            },
        },
    ]

    with patch.object(engine, "_verify_tool_result", return_value={"status": "UNVERIFIED"}), \
         patch.object(engine, "_invoke_tool", return_value={"success": True, "error": None, "data": {"used": "MG Road, Bengaluru"}}) as invoke:
        result = engine.execute(workflow)

    assert result["executed"] == ["restaurant_search"]
    assert invoke.call_args.args[1]["location"] == "MG Road, Bengaluru"


def test_engine_does_not_execute_when_required_binding_is_missing():
    db = MagicMock()
    db.get.return_value = None
    engine = WorkflowEngine(db, MagicMock(id=5), tool_registry=FakeRegistry())
    workflow = MagicMock(id=10, goal_id=20, status="PLANNED")
    workflow.steps_json = [
        {"id": "hotel_search", "tool": "search_hotels", "params": {},
         "depends_on": [], "status": "COMPLETED", "result": {"items": []}},
        {"id": "restaurant_search", "tool": "consume_location", "params": {},
         "depends_on": ["hotel_search"], "status": "PENDING",
         "input_bindings": {"location": {"source_step": "hotel_search",
                                            "source_path": "items.0.address",
                                            "required": True}}},
    ]

    with patch.object(engine, "_invoke_tool") as invoke:
        result = engine.execute(workflow)

    assert result["executed"] == []
    assert workflow.steps_json[1]["status"] == "FAILED"
    assert "Could not resolve input binding" in workflow.steps_json[1]["error"]
    invoke.assert_not_called()


def test_binding_can_require_verified_source_output():
    db = MagicMock()
    db.get.return_value = None
    engine = WorkflowEngine(db, MagicMock(id=5), tool_registry=FakeRegistry())
    step = {
        "id": "consumer", "tool": "consume_location", "params": {},
        "depends_on": ["source"],
        "input_bindings": {"location": {
            "source_step": "source", "source_path": "address",
            "required": True, "requires_verified": True,
        }},
    }
    steps = [
        {"id": "source", "status": "COMPLETED", "result": {"address": "Bengaluru"},
         "verification": {"status": "UNVERIFIED"}},
        step,
    ]

    with pytest.raises(ValueError, match="requires verified output"):
        engine._inject_dependency_results(step, steps)


def test_planner_rejects_binding_to_non_dependency():
    class PlannerTool:
        name = "consume_location"
        description = "Consume a location"
        capability = "test"
        input_schema = ConsumerInput
        requires_confirmation = False
        is_mutating = False
        execution_status = "available"

    class PlannerRegistry:
        def get(self, name):
            return PlannerTool() if name == "consume_location" else None

    planner = UniversalTaskPlanner(provider=MagicMock(), tool_registry=PlannerRegistry())
    result = planner._build_plan({"steps": [
        {"id": "source", "tool": "consume_location", "params": {"location": "A"}},
        {"id": "consumer", "tool": "consume_location", "params": {}, "depends_on": [],
         "input_bindings": {"location": {"source_step": "source", "source_path": "location"}}},
    ]}, [{"name": "consume_location", "execution_status": "available"}])

    assert isinstance(result, dict)
    assert result["decision"] == "clarification"
    assert "depends_on" in result["reply"]


def test_approval_is_bound_to_resolved_dependency_values():
    class ApprovalInput(BaseModel):
        destination: str

    class ApprovalTool:
        requires_confirmation = True
        is_mutating = True
        input_schema = ApprovalInput
        confirmation_prompt = lambda self, params: f"book transport to {params.destination}"

    class ApprovalRegistry:
        def get(self, name):
            return ApprovalTool() if name == "create_transport" else None

        def dispatch(self, ctx, name, params):
            return SimpleNamespace(success=True, message="done", data={"ok": True})

    db = MagicMock()
    db.get.return_value = None
    engine = WorkflowEngine(db, MagicMock(id=8), tool_registry=ApprovalRegistry())
    workflow = MagicMock(id=11, goal_id=21, status="PLANNED")
    workflow.steps_json = [
        {"id": "flight", "tool": "search_flight", "params": {}, "depends_on": [],
         "status": "COMPLETED", "result": {"arrival_airport": "BLR"}},
        {"id": "cab", "tool": "create_transport", "params": {},
         "depends_on": ["flight"], "status": "PENDING", "approval_required": True,
         "input_bindings": {"destination": {"source_step": "flight",
                                               "source_path": "arrival_airport",
                                               "required": True}}},
    ]

    first = engine.execute(workflow)
    assert first["workflow_status"] == "AWAITING_APPROVAL"
    assert "BLR" in workflow.steps_json[1]["approval_prompt"]
    assert engine.approve_step(workflow, "cab") is True

    # A changed upstream result invalidates the old approval and requires a fresh one.
    workflow.steps_json[0]["result"]["arrival_airport"] = "BOM"
    with patch.object(engine, "_invoke_tool") as invoke:
        second = engine.execute(workflow)

    assert second["workflow_status"] == "AWAITING_APPROVAL"
    assert "BOM" in workflow.steps_json[1]["approval_prompt"]
    invoke.assert_not_called()


def test_planner_accepts_required_parameter_supplied_by_binding():
    class PlannerTool:
        name = "consume_location"
        description = "Consume a location"
        capability = "test"
        input_schema = ConsumerInput
        requires_confirmation = False
        is_mutating = False
        execution_status = "available"

    class PlannerRegistry:
        def get(self, name):
            return PlannerTool() if name == "consume_location" else None

    planner = UniversalTaskPlanner(provider=MagicMock(), tool_registry=PlannerRegistry())
    result = planner._build_plan({"steps": [
        {"id": "hotel_search", "tool": "consume_location", "params": {"location": "Bengaluru"}},
        {"id": "restaurant_search", "tool": "consume_location", "params": {},
         "depends_on": ["hotel_search"],
         "input_bindings": {"location": {"source_step": "hotel_search",
                                             "source_path": "location",
                                             "required": True}}},
    ]}, [{"name": "consume_location", "execution_status": "available"}])

    assert isinstance(result, WorkflowPlan)
    assert result.steps[1].params == {}
    assert result.steps[1].input_bindings["location"].source_step == "hotel_search"
