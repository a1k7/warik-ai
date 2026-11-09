"""Schemas for the Warik AI trip planner (Phase 4 accuracy upgrade)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

BudgetClass = Literal["VERIFIED_QUOTE", "USER_PROVIDED", "ESTIMATE", "UNAVAILABLE"]
DaySlot = Literal["morning", "afternoon", "evening"]

class BudgetItem(BaseModel):
    category: str
    amount: Optional[float] = None
    currency: str = "INR"
    classification: BudgetClass
    note: Optional[str] = None

class TripBudget(BaseModel):
    items: list[BudgetItem] = Field(default_factory=list)
    user_budget: Optional[float] = None
    travellers: int = 1
    total_estimate: Optional[float] = None
    remaining: Optional[float] = None
    per_person: Optional[float] = None
    excludes: list[str] = Field(default_factory=list)
    is_partial: bool = False

class ItineraryActivity(BaseModel):
    name: str
    description: str = ""
    slot: DaySlot = "morning"
    suggested_time: Optional[str] = None
    duration_min: Optional[int] = None
    opening_hours: Optional[str] = None
    entry_fee: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    source: str = "Geoapify/OSM"
    map_url: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    image_credit: Optional[str] = None
    image_source_url: Optional[str] = None
    verification: dict[str, bool] = Field(default_factory=dict)

class MealSuggestion(BaseModel):
    name: str
    category: Optional[str] = None
    address: Optional[str] = None
    map_url: Optional[str] = None
    source: str = "Geoapify/OSM"

class ItineraryDay(BaseModel):
    day: int
    date: Optional[str] = None
    title: str
    city: str = ""
    morning: list[ItineraryActivity] = Field(default_factory=list)
    afternoon: list[ItineraryActivity] = Field(default_factory=list)
    evening: list[ItineraryActivity] = Field(default_factory=list)
    meal_suggestions: list[MealSuggestion] = Field(default_factory=list)
    transport_notes: list[str] = Field(default_factory=list)
    daily_budget_note: Optional[str] = None


class HotelItem(BaseModel):
    name: str
    address: str = ""
    price: str = "Not available"
    rating: str = "Not provided"
    booking_url: str = ""
    image_url: str = ""
    city: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    price_per_night: Optional[str] = None

class StructuredItinerary(BaseModel):
    type: Literal["advanced_itinerary"] = "advanced_itinerary"
    destination: str
    travellers: int = 1
    days: list[ItineraryDay] = Field(default_factory=list)
    budget: TripBudget = Field(default_factory=TripBudget)
    notes: list[str] = Field(default_factory=list)
    hotels: list[HotelItem] = Field(default_factory=list)  # NEW
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class ReplaceActivityRequest(BaseModel):
    destination: str
    slot: DaySlot
    current_activity_name: str
    used_place_names: list[str] = Field(default_factory=list)