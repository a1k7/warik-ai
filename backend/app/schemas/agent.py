from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[int] = None


class ToolCallInfo(BaseModel):
    tool_name: str
    args: dict[str, Any]
    success: bool
    message: str


class AgentMessageResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    needs_confirmation: bool = False
    confirmation_token: Optional[str] = None
    pending_tool: Optional[str] = None
    pending_args: Optional[dict[str, Any]] = None
    conversation_id: Optional[int] = None


class AgentConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=10)