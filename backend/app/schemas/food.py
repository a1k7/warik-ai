from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime

# ==========================================
# 1. DISCOVERY SCHEMAS (Used by food_tools.py)
# ==========================================
class RestaurantResult(BaseModel):
    name: str
    address: str
    cuisine: Optional[str] = None
    rating: Optional[float] = None
    distance_km: Optional[float] = None
    maps_url: str
    zomato_url: Optional[str] = None
    swiggy_url: Optional[str] = None
    status: str = "OSM_RESULT"
    is_saved: bool = False

class FoodDiscoveryResponse(BaseModel):
    type: str = "food_list"
    items: List[RestaurantResult]
    search_context: Dict[str, str]

class RestaurantComparison(BaseModel):
    type: str = "food_comparison"
    restaurants: List[RestaurantResult]
    recommendation: str

# ==========================================
# 2. EXISTING SCHEMAS (Used by app/api/food.py)
# ==========================================
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
