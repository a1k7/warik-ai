"""Warik AI LLM provider — Ollama primary + Groq fallback."""
import json
import logging
from typing import List, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are Warik AI, an intelligent Indian personal AI companion.

You handle any task: explanations, coding, writing, translation, research, recipes, advice, comparisons, math, general knowledge.

RULES:
1. Answer the question DIRECTLY.
2. If code is required, write complete working code.
3. Format with markdown — headers, code blocks, bullets, tables.
4. Be concise but complete.
5. If you don't know something, say so honestly. Do NOT hallucinate facts, prices, citations, URLs, restaurant names, or hotel details.
6. For math/calculations, show your steps so the user can verify.
7. Never invent a business, menu, price, or availability — if you don't have verified data, say so.
"""


class OllamaProvider:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def _call(self, system: str, user: str, force_json: bool = False) -> str:
        """Raw call to Ollama (used by goal_interpreter)."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3 if force_json else 0.7},
                }
                if force_json:
                    payload["format"] = "json"

                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "")
        except Exception as exc:
            logger.error("Ollama _call failed: %s", exc)
            return "LLM_FAILED"

    async def synthesize(self, history: list, tool_context: str = "") -> str:
        messages = [{"role": "system", "content": SYNTHESIS_PROMPT}]
        for msg in history[-8:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        if tool_context and tool_context != "No tools used.":
            messages.append({"role": "system", "content": f"Verified data (use this, don't invent):\n{tool_context}"})

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={"model": self.model, "messages": messages, "stream": False,
                          "options": {"temperature": 0.7}},
                )
                response.raise_for_status()
                content = response.json().get("message", {}).get("content", "").strip()
                if content:
                    return content
                raise ValueError("Empty response from Ollama")
        except Exception as exc:
            logger.warning("Ollama failed (%s), falling back to Groq", exc)
            return await self._groq_fallback(messages)

    async def _groq_fallback(self, messages: list) -> str:
        api_key = getattr(settings, "groq_api_key", None)
        if not api_key:
            return (
                "I'm having trouble reaching my local model right now. "
                "Please make sure Ollama is running (`ollama list` should show your model)."
            )

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2000,
                    },
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.error("Groq fallback also failed: %s", exc)
            return "I'm having trouble reaching my AI models right now. Please try again."

    def generate(self, prompt: str, format: str = "text") -> Optional[str]:
        try:
            with httpx.Client(timeout=60.0) as client:
                payload = {"model": self.model, "prompt": prompt, "stream": False,
                           "options": {"temperature": 0.5}}
                if format == "json":
                    payload["format"] = "json"
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
        except Exception as exc:
            logger.error("Ollama generate failed: %s", exc)
            return None


def get_provider() -> OllamaProvider:
    return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)