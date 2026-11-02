import httpx
import traceback
from dataclasses import dataclass
from typing import Optional, Any
from app.services.gnani_stt import STTResult, GnaniSTTError

class GroqSTTClient:
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout

    async def transcribe(self, audio_bytes: bytes, filename: str, content_type: Optional[str], language_code: str) -> STTResult:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        # Map language codes (e.g., "en-IN" -> "en")
        lang = language_code.split("-")[0] if language_code else "en"
        
        files = {"file": (filename or "audio.webm", audio_bytes, content_type or "audio/webm")}
        data = {"model": "whisper-large-v3", "language": lang}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    data=data,
                    files=files
                )
                
            if response.status_code != 200:
                raise GnaniSTTError(f"Groq STT returned HTTP {response.status_code}: {response.text}")
                
            body = response.json()
            transcript = body.get("text", "").strip()
            if not transcript:
                raise GnaniSTTError("Groq STT returned an empty transcript")
                
            return STTResult(transcript=transcript, request_id=None, raw=body)
            
        except GnaniSTTError:
            raise
        except Exception as e:
            # Catch all network errors (timeouts, connection refused, etc.)
            error_msg = f"Groq Network Error: {str(e)}\n{traceback.format_exc()}"
            raise GnaniSTTError(error_msg)