"""Booking API placeholder.

Actual provider-backed booking and payment integrations are not connected yet.
This endpoint intentionally refuses to manufacture a successful transaction.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Any

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User

router = APIRouter(prefix="/bookings", tags=["bookings"])


class BookingRequest(BaseModel):
    booking_type: str = Field(min_length=1, max_length=40)
    item_name: str = Field(min_length=1, max_length=240)
    amount: float = Field(ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/confirm", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def confirm_booking(
    payload: BookingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Refuse fake confirmation until a real provider/payment adapter exists."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Provider-backed booking and payment are not integrated yet. "
            "No payment has been processed and no reservation has been created."
        ),
    )
