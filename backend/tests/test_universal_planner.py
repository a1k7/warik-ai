"""Tests for capability-driven planning and safe workflow validation."""
import json
from datetime import date

from app.agents.universal_planner import UniversalTaskPlanner
from app.tools.registry import registry


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def _call(self, system, user, force_json=False):
        self.calls.append((system, user, force_json))
        if isinstance(self.response, list):
            return self.response.pop(0)
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

    async def fake_interpret(self, user_message, conversation_context="", current_date=None):
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



def test_orchestrator_passes_explicit_profile_defaults_as_advisory_context(db_session, monkeypatch):
    import asyncio
    from app.agents import orchestrator
    from app.models import User, UserPreference
    from app.core.security import hash_password

    user = User(
        email="profile-context@example.com",
        name="Profile Context Test",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(UserPreference(
        user_id=user.id,
        preferred_language="hi-IN",
        default_currency="INR",
        timezone="Asia/Kolkata",
        monthly_budget=25000,
    ))
    db_session.commit()

    captured = {}

    async def fake_interpret(self, user_message, conversation_context="", current_date=None):
        captured["context"] = conversation_context
        return {"decision": "chat", "reply": "I can help with that."}

    monkeypatch.setattr(orchestrator.UniversalTaskPlanner, "interpret", fake_interpret)
    monkeypatch.setattr(orchestrator, "parse_deterministic", lambda _text: None)
    monkeypatch.setattr(orchestrator, "get_provider", lambda: object())

    response = asyncio.run(
        orchestrator.handle_message(db_session, user, "Help me plan my monthly spending")
    )

    assert response.reply == "I can help with that."
    assert "USER PROFILE DEFAULTS" in captured["context"]
    assert "hi-IN" in captured["context"]
    assert "INR" in captured["context"]
    assert "Asia/Kolkata" in captured["context"]
    assert "local_datetime" in captured["context"]
    assert "25000" in captured["context"]
    assert "latest request overrides" in captured["context"]



def test_interpret_uses_the_callers_local_calendar_date():
    provider = FakeProvider(json.dumps({
        "decision": "chat",
        "reply": "I can help with your plan.",
    }))
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)

    result = __import__("asyncio").run(
        planner.interpret(
            "What should I prepare for tomorrow?",
            current_date=date(2026, 12, 11),
        )
    )

    assert result == {
        "decision": "chat",
        "reply": "I can help with your plan.",
        "plan": None,
    }
    assert "CURRENT DATE: 2026-12-11" in provider.calls[0][0]



def test_prompt_manifest_removes_schema_noise_but_keeps_tool_contract():
    planner = _planner()
    manifest = planner._capability_manifest()
    prompt_manifest = planner._prompt_manifest(manifest)
    task = next(item for item in prompt_manifest if item["name"] == "create_task")

    assert "properties" in task["input_schema"]
    assert "title" in task["input_schema"]["properties"]
    assert "title" in task["input_schema"].get("required", [])
    assert "$schema" not in task["input_schema"]
    full_task = next(item for item in manifest if item["name"] == "create_task")
    assert task["is_mutating"] is bool(full_task["is_mutating"])
    assert task["requires_confirmation"] is bool(full_task["requires_confirmation"])


def test_interpret_repairs_invalid_json_once():
    from asyncio import run

    provider = FakeProvider([
        "This is not valid JSON",
        json.dumps({"decision": "chat", "reply": "Hello from the repaired response."}),
    ])
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)

    result = run(planner.interpret("Hello"))

    assert result == {
        "decision": "chat",
        "reply": "Hello from the repaired response.",
        "plan": None,
    }
    assert len(provider.calls) == 2
    assert provider.calls[0][2] is True
    assert provider.calls[1][2] is True
    assert "OUTPUT REPAIR MODE" in provider.calls[1][0]
    assert "Previous invalid model output" in provider.calls[1][1]


def test_interpret_accepts_json_with_a_short_preamble_and_fence():
    provider = FakeProvider(
        'Here is the result:\n```json\n'
        + json.dumps({"decision": "chat", "reply": "Ready."})
        + '\n```'
    )
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)

    result = __import__("asyncio").run(planner.interpret("Hi"))

    assert result == {"decision": "chat", "reply": "Ready.", "plan": None}
    assert len(provider.calls) == 1



def test_disabled_capability_is_never_executable():
    planner = _planner()
    manifest = planner._capability_manifest()
    task = next(item for item in manifest if item["name"] == "list_tasks")
    task["execution_status"] = "disabled"

    result = planner._build_plan(
        {
            "steps": [{
                "id": "tasks",
                "tool": "list_tasks",
                "params": {},
            }]
        },
        manifest,
    )

    assert result["decision"] == "clarification"
    assert "disabled" in result["reply"]



def test_compact_schema_preserves_tool_defaults_and_property_names():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "examples": [{"title": "example"}],
        "properties": {
            "title": {
                "title": "Task title",
                "type": "string",
                "default": "Untitled",
            }
        },
    }

    compact = UniversalTaskPlanner._compact_schema(schema)

    assert "$schema" not in compact
    assert "examples" not in compact
    assert compact["properties"]["title"]["title"] == "Task title"
    assert compact["properties"]["title"]["default"] == "Untitled"



def test_plain_explanation_does_not_require_registered_capability():
    assert not UniversalTaskPlanner.requires_registered_capability(
        "Explain how overnight trains work."
    )


def test_real_world_trip_planning_requires_registered_capability():
    assert UniversalTaskPlanner.requires_registered_capability(
        "Plan a 3-day trip from Bhopal to Jaipur with hotels and train travel."
    )


def test_action_request_that_model_routes_to_chat_is_replanned():
    provider = FakeProvider([
        json.dumps({"decision": "chat", "reply": "Here is a made-up train plan."}),
        json.dumps({
            "decision": "clarification",
            "reply": "Which exact travel dates should I use?",
        }),
    ])
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)

    result = __import__("asyncio").run(
        planner.interpret(
            "Plan a 3-day trip from Bhopal to Jaipur.",
            current_date=date(2026, 11, 17),
        )
    )

    assert result["decision"] == "clarification"
    assert result["reply"] == "Which exact travel dates should I use?"
    assert len(provider.calls) == 2
    assert "MANDATORY EXECUTION BOUNDARY" in provider.calls[1][0]


def test_action_request_fails_closed_when_model_keeps_returning_chat():
    provider = FakeProvider([
        json.dumps({"decision": "chat", "reply": "Bhopal Jaipur Express leaves at 10 PM."}),
        json.dumps({"decision": "chat", "reply": "More unverified claims."}),
    ])
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)

    result = __import__("asyncio").run(
        planner.interpret(
            "Plan a 3-day trip from Bhopal to Jaipur, with an overnight train.",
            current_date=date(2026, 11, 17),
        )
    )

    assert result["decision"] == "clarification"
    assert "Which exact travel dates" in result["reply"]
    assert result["structured_data"]["type"] == "reliability_checkpoint"
    assert result["structured_data"]["execution_claims_allowed"] is False
    assert result["structured_data"]["missing_information"] == ["exact travel dates"]
    assert "December 2026" in result["reply"]
    assert len(provider.calls) == 2


def test_action_request_can_be_replanned_into_a_registered_workflow():
    provider = FakeProvider([
        json.dumps({"decision": "chat", "reply": "Here are your tasks."}),
        json.dumps({
            "decision": "workflow",
            "plan": {
                "goal_title": "List my open tasks",
                "goal_description": "Retrieve active tasks",
                "context": {},
                "steps": [{
                    "id": "tasks",
                    "description": "List open tasks",
                    "tool": "list_tasks",
                    "params": {"include_completed": False},
                }],
            },
        }),
    ])
    planner = UniversalTaskPlanner(provider=provider, tool_registry=registry)

    result = __import__("asyncio").run(
        planner.interpret("Find my open tasks.")
    )

    assert result["decision"] == "workflow"
    assert result["plan"].steps[0].tool == "list_tasks"
    assert len(provider.calls) == 2
