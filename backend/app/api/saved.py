from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User, SavedTrip
from app.schemas.saved import SavedTripResponse, SaveTripRequest

router = APIRouter(prefix="/saved", tags=["saved"])

@router.get("/trips", response_model=List[SavedTripResponse])
def get_saved_trips(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(SavedTrip).filter(SavedTrip.user_id == user.id).order_by(SavedTrip.created_at.desc()).all()

@router.post("/trips", response_model=SavedTripResponse)
def save_trip(payload: SaveTripRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    trip = SavedTrip(
        user_id=user.id,
        destination=payload.destination,
        days=payload.days,
        budget=payload.budget,
        itinerary_data=payload.itinerary_data
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip
