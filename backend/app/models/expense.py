from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey
from app.database.base import Base

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(8), default="INR")
    category = Column(String(60), nullable=False)
    description = Column(String(2000), nullable=True)
    expense_date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)