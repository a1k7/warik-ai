from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    remind_at: datetime


class ReminderUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    remind_at: Optional[datetime] = None
    completed: Optional[bool] = None


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    notes: Optional[str]
    remind_at: datetime
    completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime