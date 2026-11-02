from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: str = Field(min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=2000)
    expense_date: Optional[date] = None
    currency: str = Field(default="INR", max_length=8)


class ExpenseUpdate(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    category: Optional[str] = Field(default=None, min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=2000)
    expense_date: Optional[date] = None
    currency: Optional[str] = Field(default=None, max_length=8)


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: Decimal
    currency: str
    category: str
    description: Optional[str]
    expense_date: date
    created_at: datetime
    updated_at: datetime