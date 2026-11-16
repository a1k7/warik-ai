"""API schemas for the Warik Action Ledger."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CommitmentStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class CommitmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=4000)
    counterparty: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    source: str = Field(default="manual", max_length=30)


class CommitmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=4000)
    counterparty: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None
    status: CommitmentStatus | None = None
    verification_note: str | None = Field(default=None, min_length=3, max_length=2000)


class CommitmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    details: str | None
    counterparty: str | None
    due_at: datetime | None
    status: str
    source: str
    verification_note: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime
