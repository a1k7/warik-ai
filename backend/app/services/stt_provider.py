"""Replaceable STT provider. The Null provider keeps the rest of the app
usable when voice is disabled or unconfigured — no network call, no credit.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.core.config import settings
from app.services.gnani_stt import GnaniSTTClient, GnaniSTTError, STTResult
from app.services.groq_stt import GroqSTTClient

SUPPORTED_STT_LANGUAGES: frozenset[str] = frozenset(
    {
        "bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN",
        "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN",
    }
)

class STTNotConfiguredError(Exception):
    """Raised when voice is disabled or the API key is missing."""

class STTProvider(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str],
        language_code: str,
    ) -> STTResult:
        ...

class NullSTTProvider(STTProvider):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def transcribe(self, audio_bytes, filename, content_type, language_code) -> STTResult:
        raise STTNotConfiguredError(self.reason)

class GnaniSTTProvider(STTProvider):
    def __init__(self, client: GnaniSTTClient) -> None:
        self.client = client

    async def transcribe(self, audio_bytes, filename, content_type, language_code) -> STTResult:
        return await self.client.transcribe(audio_bytes, filename, content_type, language_code)

class GroqSTTProvider(STTProvider):
    def __init__(self, client: GroqSTTClient) -> None:
        self.client = client

    async def transcribe(self, audio_bytes, filename, content_type, language_code) -> STTResult:
        return await self.client.transcribe(audio_bytes, filename, content_type, language_code)


def get_stt_provider() -> STTProvider:
    if not settings.voice_enabled:
        return NullSTTProvider(
            "Voice is disabled. Set VOICE_ENABLED=true in backend/.env to enable."
        )
    
    # PREFER GROQ FOR STT (handles webm/mp4 from browsers perfectly)
    if settings.groq_api_key:
        return GroqSTTProvider(GroqSTTClient(api_key=settings.groq_api_key))
    
    # Fallback to Gnani if Groq is not configured
    if not settings.gnani_api_key:
        return NullSTTProvider("Neither GROQ_API_KEY nor GNANI_API_KEY is configured in backend/.env.")
        
    return GnaniSTTProvider(
        GnaniSTTClient(
            api_key=settings.gnani_api_key,
            stt_url=settings.gnani_stt_url,
            org_id=settings.gnani_org_id,
            user_id=settings.gnani_user_id,
        )
    )