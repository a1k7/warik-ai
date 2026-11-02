from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import Expense, User, UserPreference
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post("/", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExpenseResponse:
    expense = Expense(
        user_id=user.id,
        amount=payload.amount,
        currency=payload.currency,
        category=payload.category,
        description=payload.description,
        expense_date=payload.expense_date or date.today(),
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.get("/", response_model=list[ExpenseResponse])
def list_expenses(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ExpenseResponse]:
    query = db.query(Expense).filter(Expense.user_id == user.id)
    
    if start_date is not None:
        query = query.filter(Expense.expense_date >= start_date)
    if end_date is not None:
        query = query.filter(Expense.expense_date <= end_date)
    if category is not None:
        query = query.filter(Expense.category == category)

    query = query.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
    expenses = query.all()
    return [ExpenseResponse.model_validate(e) for e in expenses]


@router.get("/summary")
def expense_summary(
    period: Literal["today", "week", "month"] = Query(default="today"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = date.today()
    if period == "today":
        start = today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
    else:
        start = today.replace(day=1)

    # Calculate total
    total = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == user.id,
        Expense.expense_date >= start,
        Expense.expense_date <= today,
    ).scalar()
    total_dec = Decimal(str(total or 0))

    # Calculate category breakdown
    rows = (
        db.query(Expense.category, func.sum(Expense.amount))
        .filter(
            Expense.user_id == user.id,
            Expense.expense_date >= start,
            Expense.expense_date <= today,
        )
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    return {
        "period": period,
        "total": total_dec,
        "by_category": [
            {"category": cat, "amount": Decimal(str(amt))} for cat, amt in rows
        ],
    }


@router.get("/budget-status")
def budget_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if pref is None or pref.monthly_budget is None:
        return {"budget": None, "spent": Decimal("0"), "percentage": 0.0, "warning": False}

    today = date.today()
    start_of_month = today.replace(day=1)

    total = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == user.id,
        Expense.expense_date >= start_of_month,
        Expense.expense_date <= today,
    ).scalar()
    spent = Decimal(str(total or 0))
    budget = pref.monthly_budget

    percentage = float((spent / budget) * 100) if budget > 0 else 0.0
    warning = spent > (budget * Decimal("0.8"))  # Warning at 80%

    return {
        "budget": budget,
        "spent": spent,
        "percentage": round(percentage, 2),
        "warning": warning,
    }


@router.put("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExpenseResponse:
    expense = db.get(Expense, expense_id)
    if expense is None or expense.user_id != user.id:
        raise HTTPException(status_code=404, detail="Expense not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(expense, key, value)

    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    expense = db.get(Expense, expense_id)
    if expense is None or expense.user_id != user.id:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    db.delete(expense)
    db.commit()