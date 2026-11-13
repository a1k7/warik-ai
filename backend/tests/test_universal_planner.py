"""Tests for capability-driven planning and safe workflow validation."""
import json

from app.agents.universal_planner import UniversalTaskPlanner
from app.tools.registry import registry


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def _call(self, system, user, force_json=False):
        self.calls.append((system, user, force_json))
        return self.response


def _planner(response='{}'):
    return UniversalTaskPlanner(provider=FakeProvider(response), tool_registry=registry)


def test_registry_exposes_live_capability_manifest():
    manifest = registry.describe_tools()
    names = {item["name"] for item in manifest}
    assert "generate_advanced_itinerary" in names
    assert "discover_food" in names
    assert "create_task" in names
    assert all("input_schema" in item for item in manifest)


def test_planner_builds_schema_validated_workflow():
    planner = _planner()
    result = planner._build_plan(
        {
            "goal_title": "Create task",
            "goal_description": "Create a reminder task",
            "context": {},
            "steps": [{
                "id": "task",
                "description": "Create a task",
                "tool": "create_task",
                "params": {"title": "Buy groceries"},
                "depends_on": [],
            }],
        },
        planner._capability_manifest(),
    )
    assert result.steps[0].tool == "create_task"
    assert result.steps[0].params["title"] == "Buy groceries"


def test_planner_rejects_unregistered_tools():
    planner = _planner()
    result = planner._build_plan(
        {"steps": [{"id": "x", "tool": "invented_tool", "params": {}}]},
        planner._capability_manifest(),
    )
    assert result["decision"] == "clarification"
    assert "registered" in result["reply"]


def test_planner_asks_for_missing_required_parameters():
    planner = _planner()
    result = planner._build_plan(
        {"steps": [{"id": "task", "tool": "create_task", "params": {}}]},
        planner._capability_manifest(),
    )
    assert result["decision"] == "clarification"
    assert "title" in result["reply"]


def test_planner_rejects_dependency_cycles():
    planner = _planner()
    result = planner._build_plan(
        {"steps": [
            {"id": "a", "tool": "list_tasks", "params": {}, "depends_on": ["b"]},
            {"id": "b", "tool": "list_tasks", "params": {}, "depends_on": ["a"]},
        ]},
        planner._capability_manifest(),
    )
    assert result["decision"] == "clarification"
    assert "cycle" in result["reply"]


def test_confirmation_required_tool_is_marked_for_approval():
    planner = _planner()
    result = planner._build_plan(
        {"steps": [{
            "id": "expense",
            "tool": "add_expense",
            "params": {"amount": 250, "category": "Food"},
        }]},
        planner._capability_manifest(),
    )
    assert result.steps[0].approval_required is True


def test_interpret_returns_chat_decision():
    provider = FakeProvider(json.dumps({"decision": "chat", "reply": "Hello!"}))
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)
    import asyncio
    result = asyncio.run(planner.interpret("Hello"))
    assert result == {"decision": "chat", "reply": "Hello!", "plan": None}
    assert provider.calls and provider.calls[0][2] is True


def test_orchestrator_uses_universal_planner_for_unmatched_request(db_session, monkeypatch):
    import asyncio
    from app.agents import orchestrator
    from app.models import User
    from app.core.security import hash_password
    from app.schemas.workflow import WorkflowPlan, WorkflowStep

    user = User(
        email="universal-planner@example.com",
        name="Planner Test",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    plan = WorkflowPlan(
        goal_title="List open tasks",
        goal_description="Retrieve the user's open tasks",
        context={},
        steps=[WorkflowStep(
            id="tasks",
            description="List open tasks",
            tool="list_tasks",
            params={"include_completed": False},
        )],
    )

    async def fake_interpret(self, user_message, conversation_context=""):
        return {"decision": "workflow", "reply": None, "plan": plan}

    monkeypatch.setattr(orchestrator.UniversalTaskPlanner, "interpret", fake_interpret)
    monkeypatch.setattr(orchestrator, "parse_deterministic", lambda _text: None)
    monkeypatch.setattr(orchestrator, "get_provider", lambda: object())

    response = asyncio.run(
        orchestrator.handle_message(db_session, user, "show my open tasks")
    )

    assert response.structured_data is not None
    assert response.structured_data["type"] == "workflow_status"
    assert response.structured_data["status"] == "COMPLETED"


def test_optional_step_with_missing_parameters_is_skipped():
    planner = _planner()

    result = planner._build_plan(
        {
            "steps": [
                {
                    "id": "source",
                    "tool": "list_tasks",
                    "params": {},
                    "required": True,
                },
                {
                    "id": "optional_task",
                    "tool": "create_task",
                    "params": {},
                    "depends_on": ["source"],
                    "required": False,
                },
            ]
        },
        planner._capability_manifest(),
    )

    assert not isinstance(result, dict)
    assert [step.id for step in result.steps] == ["source"]


def test_optional_step_with_missing_bound_input_is_skipped():
    planner = _planner()

    result = planner._build_plan(
        {
            "steps": [
                {
                    "id": "source",
                    "tool": "list_tasks",
                    "params": {},
                    "required": True,
                },
                {
                    "id": "optional_task",
                    "tool": "create_task",
                    "params": {},
                    "input_bindings": {
                        "title": {
                            "source_step": "source",
                            "source_path": "items.0.title",
                            "required": False,
                        }
                    },
                    "depends_on": ["source"],
                    "required": False,
                },
            ]
        },
        planner._capability_manifest(),
    )

    assert not isinstance(result, dict)
    assert [step.id for step in result.steps] == ["source"]


def test_required_step_depending_on_skipped_optional_step_requests_clarification():
    planner = _planner()

    result = planner._build_plan(
        {
            "steps": [
                {
                    "id": "optional_task",
                    "tool": "create_task",
                    "params": {},
                    "required": False,
                },
                {
                    "id": "dependent",
                    "tool": "list_tasks",
                    "params": {},
                    "depends_on": ["optional_task"],
                    "required": True,
                },
            ]
        },
        planner._capability_manifest(),
    )

    assert result["decision"] == "clarification"
    assert "depends" in result["reply"]


def test_optional_step_with_unknown_parameter_is_rejected():
    planner = _planner()

    result = planner._build_plan(
        {
            "steps": [
                {
                    "id": "optional_task",
                    "tool": "create_task",
                    "params": {"unexpected_field": "value"},
                    "required": False,
                }
            ]
        },
        planner._capability_manifest(),
    )

    assert result["decision"] == "clarification"
    assert "unexpected_field" in result["reply"]


def test_optional_step_with_invalid_supplied_value_is_rejected():
    planner = _planner()

    result = planner._build_plan(
        {
            "steps": [
                {
                    "id": "optional_task",
                    "tool": "create_task",
                    "params": {"title": 12345},
                    "required": False,
                }
            ]
        },
        planner._capability_manifest(),
    )

    assert result["decision"] == "clarification"
