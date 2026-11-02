import asyncio

import pytest

from app.agents.orchestrator import handle_confirm, handle_message
from app.core.security import hash_password
from app.models import Expense, Task, User


def _user(db, email="orch@example.com") -> User:
    user = User(email=email, name="Orch", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_message_creates_task_deterministically(db_session):
    user = _user(db_session)
    response = asyncio.run(handle_message(db_session, user, "Add a task to buy groceries"))
    assert not response.needs_confirmation
    assert db_session.query(Task).filter(Task.user_id == user.id).count() == 1


def test_message_expense_requires_confirmation_then_executes(db_session):
    user = _user(db_session)

    first = asyncio.run(handle_message(db_session, user, "I spent ₹250 on lunch"))
    assert first.needs_confirmation is True
    assert first.pending_tool == "add_expense"
    assert first.confirmation_token
    assert db_session.query(Expense).filter(Expense.user_id == user.id).count() == 0

    second = asyncio.run(handle_confirm(db_session, user, first.confirmation_token))
    assert second.tool_calls and second.tool_calls[0].success
    assert db_session.query(Expense).filter(Expense.user_id == user.id).count() == 1


def test_confirm_token_rejects_different_user(db_session):
    owner = _user(db_session, "owner@example.com")
    attacker = _user(db_session, "attacker@example.com")

    first = asyncio.run(handle_message(db_session, owner, "I spent ₹100 on snacks"))
    assert first.needs_confirmation

    with pytest.raises(Exception):
        asyncio.run(handle_confirm(db_session, attacker, first.confirmation_token))