from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import func

from app.models import Expense
from app.schemas.expense import ExpenseCreate
from app.tools.base import BaseTool, ToolContext, ToolResult


class ListExpensesInput(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ExpenseSummaryInput(BaseModel):
    period: Literal["today", "week", "month"] = "today"


class AddExpenseTool(BaseTool):
    name = "add_expense"
    description = "Record an expense with an amount, category and optional description."
    input_schema = ExpenseCreate
    requires_confirmation = True

    def confirmation_prompt(self, params: ExpenseCreate) -> str:
        desc = f" ({params.description})" if params.description else ""
        return f"record ₹{params.amount} as a {params.category} expense{desc}"

    def execute(self, ctx: ToolContext, params: ExpenseCreate) -> ToolResult:
        expense = Expense(
            user_id=ctx.user.id,
            amount=params.amount,
            currency=params.currency,
            category=params.category,
            description=params.description,
            expense_date=params.expense_date or date.today(),
        )
        ctx.db.add(expense)
        ctx.db.commit()
        ctx.db.refresh(expense)
        return ToolResult(
            success=True,
            message=f"Recorded ₹{expense.amount} for {expense.category} on {expense.expense_date:%d %b %Y}.",
            data={"expense_id": expense.id, "amount": str(expense.amount)},
        )


class ListExpensesTool(BaseTool):
    name = "list_expenses"
    description = "List expenses, optionally within a date range."
    input_schema = ListExpensesInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ListExpensesInput) -> ToolResult:
        query = ctx.db.query(Expense).filter(Expense.user_id == ctx.user.id)
        if params.start_date is not None:
            query = query.filter(Expense.expense_date >= params.start_date)
        if params.end_date is not None:
            query = query.filter(Expense.expense_date <= params.end_date)
        expenses = query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(50).all()
        if not expenses:
            return ToolResult(
                success=True,
                message="No expenses recorded for that range.",
                data={"expenses": []},
            )
        lines = [
            f"- ₹{e.amount} {e.category}"
            + (f" — {e.description}" if e.description else "")
            + f" ({e.expense_date:%d %b})"
            for e in expenses
        ]
        return ToolResult(
            success=True,
            message="Recent expenses:\n" + "\n".join(lines),
            data={
                "expenses": [
                    {
                        "id": e.id,
                        "amount": str(e.amount),
                        "category": e.category,
                        "description": e.description,
                        "date": e.expense_date.isoformat(),
                    }
                    for e in expenses
                ]
            },
        )


class CalculateExpenseSummaryTool(BaseTool):
    name = "calculate_expense_summary"
    description = "Calculate total expenses for today, this week or this month, with a per-category breakdown."
    input_schema = ExpenseSummaryInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ExpenseSummaryInput) -> ToolResult:
        today = date.today()
        if params.period == "today":
            start = today
        elif params.period == "week":
            start = today - timedelta(days=today.weekday())
        else:
            start = today.replace(day=1)

        total = ctx.db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.user_id == ctx.user.id,
            Expense.expense_date >= start,
            Expense.expense_date <= today,
        ).scalar()
        total_dec = Decimal(str(total or 0))

        rows = (
            ctx.db.query(Expense.category, func.sum(Expense.amount))
            .filter(
                Expense.user_id == ctx.user.id,
                Expense.expense_date >= start,
                Expense.expense_date <= today,
            )
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )

        message = f"Total spent ({params.period}): ₹{total_dec}"
        if rows:
            message += "\n" + "\n".join(f"- {cat}: ₹{amt}" for cat, amt in rows)

        return ToolResult(
            success=True,
            message=message,
            data={
                "period": params.period,
                "total": str(total_dec),
                "by_category": [
                    {"category": cat, "amount": str(Decimal(str(amt)))} for cat, amt in rows
                ],
            },
        )