"""Deterministic, bounded conversational state for follow-up requests.

This module stores only task-local context in Conversation.state_json. It does
not infer durable personal facts and never executes tools.
"""
from __future__ import annotations

import re
from typing import Any

MAX_RECENT_MESSAGES = 8
MAX_MESSAGE_CHARS = 500
MAX_CONTEXT_CHARS = 2400

_CITY_MARKERS = re.compile(
    r"\b(?:in|to|around|near|from|at)\s+([A-Z][A-Za-z.' -]{1,45}?)(?=\s+(?:for|with|on|between|under|within)\b|[,;.!?]|$)",
)
_BUDGET = re.compile(r"(?:₹|rs\.?\s*)([\d,]+)|\b(?:budget|under|below)\s*(?:of\s*)?(?:₹|rs\.?\s*)?([\d,]+)", re.I)
_DATE = re.compile(r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?:\s+\d{4})?|\d{4}-\d{2}-\d{2})\b", re.I)


def extract_task_entities(text: str) -> dict[str, Any]:
    """Extract conservative literal entities; never guess missing values."""
    value = (text or "").strip()
    entities: dict[str, Any] = {}
    city_match = _CITY_MARKERS.search(value)
    if city_match:
        candidate = re.sub(r"\s+", " ", city_match.group(1)).strip(" .,-")
        if 2 <= len(candidate) <= 45 and candidate.lower() not in {"there", "here", "it", "me"}:
            entities["location_mention"] = candidate
    budget_match = _BUDGET.search(value)
    if budget_match:
        raw = budget_match.group(1) or budget_match.group(2)
        try:
            amount = int(raw.replace(",", ""))
            if amount > 0:
                entities["budget_mention"] = amount
        except (TypeError, ValueError):
            pass
    dates = _DATE.findall(value)
    if dates:
        entities["date_mentions"] = dates[:4]
    return entities


def update_conversation_context(conversation, user_text: str) -> dict[str, Any]:
    """Merge the latest turn into conversation state without erasing other slots."""
    state = dict(getattr(conversation, "state_json", None) or {})
    context = dict(state.get("conversation_context") or {})
    context["latest_user_message"] = (user_text or "").strip()[:MAX_MESSAGE_CHARS]
    context["entities"] = {**dict(context.get("entities") or {}), **extract_task_entities(user_text)}
    context["updated_turn_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    state["conversation_context"] = context
    conversation.state_json = state
    return state


def build_conversation_context(conversation, latest_text: str = "", workflow=None) -> str:
    """Build bounded planner context from recent turns, task state and workflow."""
    lines = ["CONVERSATION CONTEXT (reference only; latest user request has priority):"]
    state = dict(getattr(conversation, "state_json", None) or {})
    task = dict(state.get("conversation_context") or {})
    entities = dict(task.get("entities") or {})
    if task.get("latest_user_message"):
        lines.append(f"Previous task request: {str(task['latest_user_message'])[:MAX_MESSAGE_CHARS]}")
    if entities:
        lines.append("Explicitly mentioned task details: " + repr(entities)[:700])
    messages = list(getattr(conversation, "messages", None) or [])
    recent = messages[-MAX_RECENT_MESSAGES:]
    if recent:
        lines.append("Recent conversation turns:")
        for message in recent:
            role = str(getattr(message, "role", "message"))[:20]
            content = str(getattr(message, "content", ""))[:MAX_MESSAGE_CHARS]
            if content:
                lines.append(f"{role}: {content}")
    if workflow is not None:
        steps = list(getattr(workflow, "steps_json", None) or [])
        summary = []
        for step in steps[:20]:
            summary.append({
                "id": step.get("id"), "description": step.get("description"),
                "status": step.get("status"), "tool": step.get("tool"),
            })
        lines.append(f"Active workflow {getattr(workflow, 'id', '')} ({getattr(workflow, 'status', 'unknown')}): {summary!r}")
    if latest_text:
        lines.append(f"LATEST USER MESSAGE (authoritative): {latest_text[:MAX_MESSAGE_CHARS]}")
    result = "\n".join(lines)
    return result[:MAX_CONTEXT_CHARS]


def is_resume_request(text: str) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", (text or "").lower()).strip()
    # Accept polite prefixes only when the remaining command is itself an
    # explicit resume phrase. Do not treat a sentence with new instructions
    # (for example, "continue but make it cheaper") as authorization to resume.
    if normalized.startswith("please "):
        normalized = normalized[len("please "):].strip()
    return normalized in {
        "continue", "continue please", "continue the plan", "continue the workflow",
        "resume", "resume please", "resume workflow", "keep going", "carry on",
        "proceed with remaining steps", "finish the remaining steps", "complete the plan",
    }
