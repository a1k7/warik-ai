"""Replaceable LLM provider layer. Groq is the default for fast cloud reasoning.
Ollama is supported as a free local fallback.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# FIXED: Escaped curly braces {{ }} and replaced em-dashes with normal hyphens
SYSTEM_PROMPT = """You are the tool router for Warik AI, a premium personal assistant for travel.

Given the user message, choose ONE intent and extract its arguments as JSON.

Intents and their argument schemas:
- create_task(title: str, description?: str, due_date?: ISO datetime, priority?: "low"|"medium"|"high", category?: str)
- list_tasks(include_completed?: bool, due_on?: "YYYY-MM-DD")
- complete_task(task_id: int)
- create_reminder(title: str, remind_at: ISO datetime, notes?: str)
- list_reminders(upcoming_hours?: int)
- add_expense(amount: decimal, category: str, description?: str, expense_date?: "YYYY-MM-DD")
- list_expenses(start_date?: "YYYY-MM-DD", end_date?: "YYYY-MM-DD")
- calculate_expense_summary(period: "today"|"week"|"month")
- create_travel_plan(title, origin, destination, start_date?, end_date?, travellers?, budget?, currency?, notes?)
- search_places_geoapify(location: str, category?: "restaurant"|"cafe"|"hotel"|"tourist_spot") - Use this to find places. ALWAYS extract the city or area name into 'location'. 
- search_flights_real(origin: str, destination: str, date: "YYYY-MM-DD") - ALWAYS use IATA codes for origin/destination.
- search_hotels_stayapi(city: str, check_in: "YYYY-MM-DD", check_out: "YYYY-MM-DD") - Ensure check_out is AFTER check_in.
- get_cab_links(pickup_location: str, dropoff_location: str)
- retrieve_memory(query: str)
- save_memory(content: str, category?: str)
- delete_memory(memory_id: int)
- chat(reply: str) - for general conversation with no tool action

Examples of correct JSON outputs:
User: "Find some good restaurants in Mumbai"
Response: {{"intent": "search_places_geoapify", "params": {{"location": "Mumbai", "category": "restaurant"}}}}

User: "Find flights from Mumbai to Delhi on 2026-11-15"
Response: {{"intent": "search_flights_real", "params": {{"origin": "BOM", "destination": "DEL", "date": "2026-11-15"}}}}

Respond with ONLY a valid JSON object of the form:
{{"intent": "<intent>", "params": {{ ... }}}}

Today is {today}. Current local time is {now} (Asia/Kolkata)."""


class LLMProvider:
    async def route(self, user_text: str) -> Optional[dict[str, Any]]:
        return None


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def route(self, user_text: str) -> Optional[dict[str, Any]]:
        now = datetime.now()
        system = SYSTEM_PROMPT.format(today=now.date().isoformat(), now=now.isoformat(timespec="seconds"))
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_text},
                        ],
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                )
                response.raise_for_status()
                content = response.json().get("message", {}).get("content", "")
                if not content:
                    return None
                parsed = json.loads(content)
                if not isinstance(parsed, dict) or "intent" not in parsed:
                    return None
                return parsed
        except Exception as exc:
            logger.info("Ollama routing unavailable: %s", exc)
            return None


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"

    async def route(self, user_text: str) -> Optional[dict[str, Any]]:
        now = datetime.now()
        system = SYSTEM_PROMPT.format(today=now.date().isoformat(), now=now.isoformat(timespec="seconds"))
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                if not content:
                    return None
                parsed = json.loads(content)
                if not isinstance(parsed, dict) or "intent" not in parsed:
                    return None
                return parsed
        except Exception as exc:
            logger.error("Groq routing failed: %s", exc)
            return None


def get_provider() -> LLMProvider:
    if getattr(settings, "llm_provider", "ollama") == "groq" and settings.groq_api_key:
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model
        )
    return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)