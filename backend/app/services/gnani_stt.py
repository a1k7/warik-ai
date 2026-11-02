"""Gnani Prisma STT v3 client.

Contract verified against:
- https://www.gnani.ai/speech-to-text-api (official payload + response)
- https://pypi.org/project/gnani-vachana/ (official Python client — headers, languages)

Do not change the multipart field names or headers without re-verifying.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

DEFAULT_TIMEOUT_SECONDS = 30.0


class GnaniSTTError(Exception):
    """Raised when Gnani STT returns an error or an unusable response."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class STTResult:
    transcript: str
    request_id: Optional[str]
    raw: dict[str, Any]


class GnaniSTTClient:
    def __init__(
        self,
        api_key: str,
        stt_url: str,
        org_id: str = "",
        user_id: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
    ) -> None:
        self.api_key = api_key
        self.stt_url = stt_url
        self.org_id = org_id
        self.user_id = user_id
        self.timeout = timeout
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=self.timeout)
        )

    def _headers(self) -> dict[str, str]:
        headers = {"X-API-Key-ID": self.api_key}
        if self.org_id:
            headers["X-Organization-ID"] = self.org_id
        if self.user_id:
            headers["X-API-User-ID"] = self.user_id
        return headers

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str],
        language_code: str,
    ) -> STTResult:
        files = {
            "audio_file": (
                filename or "audio",
                audio_bytes,
                content_type or "application/octet-stream",
            )
        }
        data = {
            "language_code": language_code,
            "preferred_language": language_code,
            "format": "transcribe",
            "itn_native_numerals": "true",
        }

        async with self._client_factory() as client:
            response = await client.post(
                self.stt_url,
                headers=self._headers(),
                data=data,
                files=files,
            )

        if response.status_code != 200:
            raise GnaniSTTError(
                f"Gnani STT returned HTTP {response.status_code}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except Exception as exc:  # noqa: BLE001 — response was not JSON
            raise GnaniSTTError(f"Gnani STT returned non-JSON response: {exc}")

        if not isinstance(body, dict) or not body.get("success"):
            raise GnaniSTTError(f"Gnani STT reported failure: {body}")

        transcript = (body.get("transcript") or "").strip()
        if not transcript:
            raise GnaniSTTError("Gnani STT returned an empty transcript")

        return STTResult(
            transcript=transcript,
            request_id=body.get("request_id"),
            raw=body,
        )