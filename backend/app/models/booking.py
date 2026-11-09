from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from app.database.base import Base

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    booking_type = Column(String, nullable=False) # e.g., "hotel", "flight"
    item_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    status = Column(String, default="CONFIRMED") # CONFIRMED, CANCELLED
    details = Column(JSON, nullable=True) # check-in dates, etc.
    created_at = Column(DateTime, default=datetime.utcnow)