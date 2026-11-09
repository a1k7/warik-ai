from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base

class SavedHotel(Base):
    __tablename__ = "saved_hotels"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    booking_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    check_in: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    check_out: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class SavedTrip(Base):
    __tablename__ = "saved_trips"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    itinerary_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
