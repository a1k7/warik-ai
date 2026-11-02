from decimal import Decimal

from app.core.security import hash_password
from app.models import Expense, Task, User
from app.tools.base import ToolContext
from app.tools.registry import registry


def _user(db, email="tools@example.com") -> User:
    user = User(email=email, name="Tools", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_task_via_registry(db_session):
    user = _user(db_session)
    ctx = ToolContext(db=db_session, user=user)
    result = registry.dispatch(ctx, "create_task", {"title": "Buy groceries"})
    assert result.success, result.message
    stored = db_session.query(Task).filter(Task.user_id == user.id).one()
    assert stored.title == "Buy groceries"


def test_add_expense_via_registry(db_session):
    user = _user(db_session)
    ctx = ToolContext(db=db_session, user=user)
    result = registry.dispatch(
        ctx,
        "add_expense",
        {"amount": "250.00", "category": "Food", "description": "Lunch"},
    )
    assert result.success, result.message
    stored = db_session.query(Expense).filter(Expense.user_id == user.id).one()
    assert stored.amount == Decimal("250.00")


def test_expense_summary_is_deterministic(db_session):
    user = _user(db_session)
    ctx = ToolContext(db=db_session, user=user)
    registry.dispatch(ctx, "add_expense", {"amount": "100", "category": "Food"})
    registry.dispatch(ctx, "add_expense", {"amount": "250.50", "category": "Transport"})
    result = registry.dispatch(ctx, "calculate_expense_summary", {"period": "today"})
    assert result.success
    assert Decimal(result.data["total"]) == Decimal("350.50")


def test_tools_are_user_scoped(db_session):
    user_a = _user(db_session, "a@example.com")
    user_b = _user(db_session, "b@example.com")
    ctx_a = ToolContext(db=db_session, user=user_a)
    ctx_b = ToolContext(db=db_session, user=user_b)
    registry.dispatch(ctx_a, "create_task", {"title": "A's task"})
    result = registry.dispatch(ctx_b, "list_tasks", {})
    assert result.success
    assert result.data.get("tasks") == []