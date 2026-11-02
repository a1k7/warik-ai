"""Replaceable TTS provider with Null fallback and disk caching."""

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.gnani_tts import GnaniTTSClient, GnaniTTSError

CACHE_DIR = Path("audio_cache")
CACHE_DIR.mkdir(exist_ok=True)


class TTSNotConfiguredError(Exception):
    pass


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, language_code: str) -> tuple[bytes, bool]:
        """Returns (audio_bytes, was_cached)."""
        ...


class NullTTSProvider(TTSProvider):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def synthesize(self, text: str, language_code: str) -> tuple[bytes, bool]:
        raise TTSNotConfiguredError(self.reason)


class GnaniTTSProvider(TTSProvider):
    def __init__(self, client: GnaniTTSClient) -> None:
        self.client = client

    def _cache_key(self, text: str, language_code: str) -> str:
        raw = f"{text}|{language_code}|{self.client.default_voice}|{self.client.default_model}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def synthesize(self, text: str, language_code: str) -> tuple[bytes, bool]:
        key = self._cache_key(text, language_code)
        cache_path = CACHE_DIR / f"{key}.wav"

        if cache_path.exists():
            return cache_path.read_bytes(), True

        audio_bytes = await self.client.generate_audio(text, language_code)
        cache_path.write_bytes(audio_bytes)
        return audio_bytes, False


def get_tts_provider() -> TTSProvider:
    if not settings.voice_enabled:
        return NullTTSProvider(
            "Voice is disabled. Set VOICE_ENABLED=true in backend/.env to enable."
        )
    if not settings.gnani_api_key:
        return NullTTSProvider(
            "GNANI_API_KEY is not configured in backend/.env."
        )
    return GnaniTTSProvider(
        GnaniTTSClient(
            api_key=settings.gnani_api_key,
            tts_url=settings.gnani_tts_url,
            default_voice=settings.gnani_tts_voice,
            default_model=settings.gnani_tts_model,
        )
    )