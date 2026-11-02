from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FoodSearchRequest(BaseModel):
    location: str = Field(min_length=1, max_length=200)
    preference: Optional[str] = Field(default=None, max_length=100)
    budget: Optional[str] = Field(default=None, max_length=50)


class FoodSearchResponse(BaseModel):
    disclaimer: str
    external_links: dict[str, str]


class FavoriteRestaurantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)


class FavoriteRestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    location: Optional[str]
    notes: Optional[str]
    created_at: datetime