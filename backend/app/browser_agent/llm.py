"""Swappable adapter around the repository's configured Ollama/Groq provider."""

import json
from typing import Any

from app.agents.llm_provider import get_provider


def call_model(messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> str | None:
    """Return a structured planner response, or None to activate the scripted fallback."""
    try:
        prompt = (
            "You are a browser task planner. Return ONLY valid JSON with keys "
            "origin, destination, date_hint, time_window, and plan_summary. "
            "Never claim live availability and never take the action.\n"
            + json.dumps({"messages": messages, "available_actions": tools or []})
        )
        result = get_provider().generate(prompt, format="json")
        return result.strip() if result else None
    except Exception:
        return None
