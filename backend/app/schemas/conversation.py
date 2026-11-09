from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict

class MessageBase(BaseModel):
    role: str
    content: str
    structured_data: Optional[dict] = None

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: int
    created_at: datetime

class ConversationCreate(BaseModel):
    title: Optional[str] = "New Chat"

class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    is_archived: Optional[bool] = None

class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = []