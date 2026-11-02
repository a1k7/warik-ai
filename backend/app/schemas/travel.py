from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TravelStopCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    arrival: Optional[datetime] = None
    departure: Optional[datetime] = None
    estimated_cost: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class TravelStopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    travel_plan_id: int
    order_index: int
    name: str
    notes: Optional[str]
    arrival: Optional[datetime]
    departure: Optional[datetime]
    estimated_cost: Optional[Decimal]


class TravelPlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    origin: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    travellers: int = Field(default=1, ge=1, le=50)
    budget: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="INR", max_length=8)
    notes: Optional[str] = Field(default=None, max_length=4000)
    stops: list[TravelStopCreate] = Field(default_factory=list)


class TravelPlanUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    origin: Optional[str] = Field(default=None, min_length=1, max_length=120)
    destination: Optional[str] = Field(default=None, min_length=1, max_length=120)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    travellers: Optional[int] = Field(default=None, ge=1, le=50)
    budget: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: Optional[str] = Field(default=None, max_length=8)
    notes: Optional[str] = Field(default=None, max_length=4000)


class TravelPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    origin: str
    destination: str
    start_date: Optional[date]
    end_date: Optional[date]
    travellers: int
    budget: Optional[Decimal]
    currency: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    stops: list[TravelStopResponse] = Field(default_factory=list)