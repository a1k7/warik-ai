from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=60)


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=60)


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    content: str
    category: Optional[str]
    source: str
    created_at: datetime
    updated_at: datetime