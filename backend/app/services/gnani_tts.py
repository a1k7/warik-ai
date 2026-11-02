"""Gnani Timbre TTS client.

Docs note:
- Endpoint: POST https://api.gnani.ai/v1/tts/inference
- Authentication: Authorization: Bearer <api_key> (NOT X-API-Key-ID)
- Payload: JSON {"text": "...", "language": "...", "voice": "...", "model": "..."}
- Response: Binary audio stream (usually WAV).
"""

from typing import Any, Callable, Optional

import httpx

DEFAULT_TIMEOUT_SECONDS = 15.0


class GnaniTTSError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GnaniTTSClient:
    def __init__(
        self,
        api_key: str,
        tts_url: str,
        default_voice: str,
        default_model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
    ) -> None:
        self.api_key = api_key
        self.tts_url = tts_url
        self.default_voice = default_voice
        self.default_model = default_model
        self.timeout = timeout
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=self.timeout)
        )

    async def generate_audio(
        self,
        text: str,
        language_code: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
    ) -> bytes:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "language": language_code,
            "voice": voice or self.default_voice,
            "model": model or self.default_model,
        }

        async with self._client_factory() as client:
            response = await client.post(self.tts_url, headers=headers, json=payload)

        if response.status_code != 200:
            raise GnaniTTSError(
                f"Gnani TTS returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            # Gnani sometimes returns JSON errors even on 200 OK
            try:
                body = response.json()
                raise GnaniTTSError(f"Gnani TTS API error: {body}")
            except Exception:
                pass

        audio_bytes = response.content
        if not audio_bytes or len(audio_bytes) < 100:
            raise GnaniTTSError("Gnani TTS returned empty or invalid audio data")

        return audio_bytes