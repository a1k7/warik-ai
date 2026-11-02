from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    category: Optional[str] = Field(default=None, max_length=60)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[datetime] = None
    priority: Optional[TaskPriority] = None
    category: Optional[str] = Field(default=None, max_length=60)
    completed: Optional[bool] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    priority: str
    category: Optional[str]
    completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime