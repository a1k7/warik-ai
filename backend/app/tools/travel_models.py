from pydantic import BaseModel
from typing import Optional

class FlightResult(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    arrival_time: str
    price: str
    currency: str
    booking_url: str

class HotelResult(BaseModel):
    name: str
    price_per_night: Optional[str] = None
    rating: Optional[str] = None
    image_url: Optional[str] = None
    booking_url: str
    map_url: str

class PlaceResult(BaseModel):
    name: str
    address: str
    map_url: str

class CabResult(BaseModel):
    provider: str
    distance_km: Optional[str] = None
    deep_link: str