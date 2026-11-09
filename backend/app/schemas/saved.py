from pydantic import BaseModel, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime
from decimal import Decimal

class SavedTripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    destination: str
    days: int
    budget: Optional[Decimal] = None
    itinerary_data: Dict[str, Any]
    created_at: datetime

class SaveTripRequest(BaseModel):
    destination: str
    days: int
    budget: Optional[float] = None
    itinerary_data: Dict[str, Any]
