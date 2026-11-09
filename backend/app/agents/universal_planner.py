"""Capability-driven planning for tasks outside legacy deterministic routes.

The planner may propose only registered tools. The registry validates every
argument, dependencies are checked server-side, and the workflow engine applies
server-side approval policy before execution.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.agents.llm_provider import get_provider
from app.schemas.workflow import WorkflowPlan
from app.tools.registry import registry

logger = logging.getLogger(__name__)

UNIVERSAL_PLANNER_PROMPT = """You are the task planner for Warik AI, a personal task operator.

CURRENT DATE/TIME (Asia/Kolkata): {current_datetime}

Convert the user's request into ONE of three decisions:
1. workflow: a concrete plan using only the registered capabilities below.
2. clarification: ask one concise question for essential missing information.
3. chat: answer normally when no tool execution is needed.

AVAILABLE CAPABILITIES (authoritative; do not invent tools):
{tools_manifest}

Return only valid JSON with this shape:
{{
  "decision": "workflow | clarification | chat",
  "reply": "answer or one clarification question, if applicable",
  "plan": {{
    "goal_title": "Short outcome-oriented title",
    "goal_description": "What the user wants completed",
    "context": {{}},
    "steps": [
      {{
        "id": "stable_step_id",
        "description": "What this step does",
        "tool": "exact registered tool name",
        "params": {{}},
        "depends_on": [],
        "approval_required": false,
        "required": true,
        "dep_policy": "all_success",
        "max_retries": 1
      }}
    ]
  }}
}}

OPERATING RULES:
- Treat the user's desired outcome as the goal; choose tools based on their schemas.
- Use only exact tool names from the registry. Never invent a provider or action.
- Never invent dates, addresses, identities, prices, availability, booking references,
  selections, or payment status. Ask for missing essential details instead.
- Use valid values for every required tool input. Do not send placeholders.
- Build dependencies only when one step genuinely needs another step's result.
- Independent discovery steps should have no dependencies on each other.
- A search tool is not a booking tool. Flight search returns options/booking links;
  hotel search returns external booking links; cab tools create handoff links; the
  food-order search tool hands off to the provider. Do not claim these actions are booked.
- Do not invent payment or checkout capabilities. If a provider handoff is required,
  explain that the user completes the provider's checkout.
- Do not assume a user preference or select among consequential alternatives for them.
  Present the choices and ask the user to select one before a consequential action.
- Mark workflow steps optional when they are supplementary. A required summary may
  depend on optional discovery steps using tolerate_failure.
- The server enforces confirmation for tools marked mutating or requiring approval.
- For normal questions, answer in the "chat" decision and do not create a workflow.
"""


class UniversalTaskPlanner:
    def __init__(self, provider=None):
        self.provider = provider or get_provider()

    async def interpret(self, user_message: str, conversation_context: str = "") -> dict:
        """Return a validated workflow, a clarification, or a chat response."""
        if not hasattr(self.provider, "_call"):
            return {"decision": "unavailable", "plan": None}

        try:
            manifest = registry.describe_tools()
            system = UNIVERSAL_PLANNER_PROMPT.format(
                tools_manifest=json.dumps(manifest, ensure_ascii=False),
                current_datetime=datetime.now(
                    ZoneInfo("Asia/Kolkata")
                ).isoformat(timespec="minutes"),
            )
            user_input = user_message
            if conversation_context:
                user_input = (
                    f"Recent conversation context:\n{conversation_context}\n\n"
                    f"Current user request:\n{user_message}"
                )
            raw = await self.provider._call(system, user_input, force_json=True)
            if not raw or raw == "LLM_FAILED":
                return {"decision": "unavailable", "plan": None}

            payload = json.loads(raw.replace("```json", "").replace("```", "").strip())
            decision = str(payload.get("decision", "")).strip().lower()

            if decision == "chat":
                return {"decision": "chat", "reply": str(payload.get("reply", "")).strip(), "plan": None}

            if decision == "clarification":
                question = str(payload.get("reply", "")).strip()
                return {
                    "decision": "clarification",
                    "reply": question or "What additional detail should I use?",
                    "plan": None,
                }

            if decision != "workflow":
                return {"decision": "unavailable", "plan": None}

            plan = WorkflowPlan.model_validate(payload.get("plan") or {})
            validation_error = self._validate_plan(plan)
            if validation_error:
                return {
                    "decision": "clarification",
                    "reply": validation_error,
                    "plan": None,
                }

            return {"decision": "workflow", "plan": plan}

        except (ValueError, TypeError, ValidationError, KeyError) as exc:
            logger.warning("Universal task plan rejected: %s", exc)
            return {"decision": "unavailable", "plan": None}
        except Exception:
            logger.exception("Universal task planner failed")
            return {"decision": "unavailable", "plan": None}

    @staticmethod
    def _validate_plan(plan: WorkflowPlan) -> str | None:
        if not plan.steps:
            return "I couldn't identify an executable action. What would you like me to do first?"
        if len(plan.steps) > 12:
            return "This request is too broad to execute safely in one workflow. Which outcome should I handle first?"

        step_ids = [step.id for step in plan.steps]
        if len(step_ids) != len(set(step_ids)):
            return "I couldn't build a safe task plan because it contains duplicate step identifiers. Please rephrase the request."

        known_ids = set(step_ids)
        graph: dict[str, list[str]] = {}

        for step in plan.steps:
            tool = registry.get(step.tool)
            if tool is None:
                return f"I can't execute '{step.description}' because that capability is not connected yet."

            status = getattr(tool, "execution_status", "available")
            if status in {"unavailable", "requires_auth"}:
                return f"The {step.tool} capability is currently {status.replace('_', ' ')}. I can't execute that step yet."

            try:
                validated = tool.input_schema(**step.params)
            except ValidationError as exc:
                first = exc.errors()[0]
                location = first.get("loc") or ("details",)
                field = str(location[0]).replace("_", " ")
                return f"I need the {field} to {step.description.lower()}."

            step.params = validated.model_dump(mode="json")
            # This is a convenience on the plan; WorkflowEngine independently
            # re-enforces the same policy at execution time.
            if (
                getattr(tool, "requires_confirmation", False)
                or getattr(tool, "is_mutating", False)
            ):
                step.approval_required = True

            dependencies = list(step.depends_on or [])
            if any(dep not in known_ids or dep == step.id for dep in dependencies):
                return f"I couldn't validate the task dependencies for '{step.description}'."
            graph[step.id] = dependencies

        # Reject cycles before persisting a workflow.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return False
            if node in visited:
                return True
            visiting.add(node)
            for dependency in graph.get(node, []):
                if not visit(dependency):
                    return False
            visiting.remove(node)
            visited.add(node)
            return True

        if not all(visit(node) for node in graph):
            return "I couldn't build a safe execution order for that request. Please simplify it into a few outcomes."
        return None
