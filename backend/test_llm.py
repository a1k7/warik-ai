import asyncio
from app.agents.llm_provider import get_provider
from app.core.config import settings

async def test():
    print(f"Configured Provider: {settings.llm_provider}")
    if settings.groq_api_key:
        print(f"Groq Key Loaded: {settings.groq_api_key[:5]}...{settings.groq_api_key[-4:]}")
    else:
        print("Groq Key: MISSING (Check your .env file!)")
        
    provider = get_provider()
    print(f"Using Provider Class: {provider.__class__.__name__}")
    
    print("Sending test message to LLM...")
    result = await provider.route("Plan a trip from Bhopal to Indore under 2000 rupees")
    print("Result:", result)

asyncio.run(test())
