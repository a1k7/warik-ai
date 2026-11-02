from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.agent import ToolCallInfo


class TranscriptionResponse(BaseModel):
    transcript: str
    request_id: Optional[str] = None
    language_code: str
    usage_seconds_used: int
    usage_seconds_limit: int


class VoiceMessageResponse(BaseModel):
    transcript: str
    reply: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    needs_confirmation: bool = False
    confirmation_token: Optional[str] = None
    pending_tool: Optional[str] = None
    pending_args: Optional[dict[str, Any]] = None


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language_code: str = Field(default="en-IN", max_length=10)