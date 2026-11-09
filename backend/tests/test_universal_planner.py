import asyncio
import json
from pydantic import BaseModel
from unittest.mock import patch

from app.agents.universal_planner import UniversalTaskPlanner
from app.tools import registry as registry_module


class SampleInput(BaseModel):
    query: str


class FakeTool:
    name = "sample_search"
    description = "Search sample data."
    capability = "research"
    input_schema = SampleInput
    requires_confirmation = False
    is_mutating = False
    execution_status = "available"


def _provider(payload):
    class Provider:
        async def _call(self, system, user, force_json=False):
            return json.dumps(payload)
    return Provider()


def test_universal_planner_accepts_registered_valid_tool():
    payload = {
        "decision": "workflow",
        "plan": {
            "goal_title": "Search",
            "goal_description": "Find sample data",
            "context": {},
            "steps": [{
                "id": "search",
                "description": "Search sample data",
                "tool": "sample_search",
                "params": {"query": "cafes"},
                "depends_on": [],
            }],
        },
    }
    planner = UniversalTaskPlanner(provider=_provider(payload))
    with patch.object(registry_module.registry, "describe_tools", return_value=[]), \
         patch.object(registry_module.registry, "get", return_value=FakeTool()):
        result = asyncio.run(planner.interpret("Find cafes"))
    assert result["decision"] == "workflow"
    assert result["plan"].steps[0].params == {"query": "cafes"}


def test_universal_planner_rejects_unregistered_tool():
    payload = {
        "decision": "workflow",
        "plan": {
            "goal_title": "Unsupported",
            "goal_description": "",
            "context": {},
            "steps": [{
                "id": "book",
                "description": "Book a flight",
                "tool": "invented_booking_tool",
                "params": {},
                "depends_on": [],
            }],
        },
    }
    planner = UniversalTaskPlanner(provider=_provider(payload))
    with patch.object(registry_module.registry, "describe_tools", return_value=[]), \
         patch.object(registry_module.registry, "get", return_value=None):
        result = asyncio.run(planner.interpret("Book a flight"))
    assert result["decision"] == "clarification"
    assert "not connected" in result["reply"]


def test_orchestrator_uses_universal_planner_for_unmatched_actions(db_session, monkeypatch):
    import asyncio
    from app.agents import orchestrator
    from app.models import User
    from app.schemas.workflow import WorkflowPlan, WorkflowStep

    user = User(
        email="universal-orchestrator@example.com",
        name="Universal Planner Test",
        password_hash="unused-test-hash",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    plan = WorkflowPlan(
        goal_title="List open tasks",
        goal_description="Show the user's open tasks",
        context={},
        steps=[
            WorkflowStep(
                id="list_tasks",
                description="List open tasks",
                tool="list_tasks",
                params={},
                depends_on=[],
            )
        ],
    )

    class FakePlanner:
        def __init__(self, provider=None):
            pass

        async def interpret(self, user_message, conversation_context=""):
            return {"decision": "workflow", "plan": plan}

    monkeypatch.setattr(orchestrator, "UniversalTaskPlanner", FakePlanner)
    monkeypatch.setattr(orchestrator, "get_provider", lambda: object())

    response = asyncio.run(
        orchestrator.handle_message(
            db_session,
            user,
            "Show me the tasks I still need to finish",
        )
    )

    assert response.structured_data is not None
    assert response.structured_data["type"] == "workflow_status"
    assert response.structured_data["status"] == "COMPLETED"
