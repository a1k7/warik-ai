from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    created_at: datetime


class RegisterResponse(BaseModel):
    user: UserPublic
    access_token: str
    token_type: str = "bearer"


class UserPreferenceUpdate(BaseModel):
    preferred_language: Optional[str] = Field(default=None, max_length=10)
    default_currency: Optional[str] = Field(default=None, max_length=8)
    timezone: Optional[str] = Field(default=None, max_length=64)
    voice_responses_enabled: Optional[bool] = None
    monthly_budget: Optional[Decimal] = Field(default=None, ge=0)


class UserPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    preferred_language: str
    default_currency: str
    timezone: str
    voice_responses_enabled: bool
    monthly_budget: Optional[Decimal]
    created_at: datetime
    updated_at: datetime