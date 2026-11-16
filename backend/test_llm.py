"""Manual LLM connectivity smoke test.

Run explicitly with `python test_llm.py`. This file is intentionally not
executed during pytest collection because it makes a live provider request.
"""

import asyncio

from app.agents.llm_provider import get_provider
from app.core.config import settings


async def run_llm_smoke_test() -> None:
    print(f"Configured Provider: {settings.llm_provider}")
    print(f"Groq Key Configured: {'yes' if settings.groq_api_key else 'no'}")

    provider = get_provider()
    print(f"Using Provider Class: {provider.__class__.__name__}")
    print("Sending test message to LLM...")

    result = await provider.synthesize(
        [
            {
                "role": "user",
                "content": (
                    "Plan a trip from Bhopal to Indore under 2000 rupees"
                ),
            }
        ]
    )
    print("Result:", result)


if __name__ == "__main__":
    asyncio.run(run_llm_smoke_test())
