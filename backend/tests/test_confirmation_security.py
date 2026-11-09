import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.agents.orchestrator import handle_confirm, handle_message
from app.core.security import hash_password
from app.models import Confirmation, Expense, User


def create_user(db, email="security@example.com"):
    user = User(
        email=email,
        name="Security Test",
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_confirmation_token_cannot_be_replayed(db_session):
    user = create_user(db_session)

    pending = asyncio.run(
        handle_message(db_session, user, "I spent ₹250 on lunch")
    )

    assert pending.needs_confirmation
    assert db_session.query(Expense).filter_by(user_id=user.id).count() == 0

    first = asyncio.run(
        handle_confirm(db_session, user, pending.confirmation_token)
    )

    assert first.tool_calls[0].success
    assert db_session.query(Expense).filter_by(user_id=user.id).count() == 1

    confirmation = (
        db_session.query(Confirmation)
        .filter_by(user_id=user.id)
        .one()
    )
    assert confirmation.status == "EXECUTED"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            handle_confirm(db_session, user, pending.confirmation_token)
        )

    assert exc.value.status_code == 409
    assert db_session.query(Expense).filter_by(user_id=user.id).count() == 1


def test_expired_confirmation_cannot_execute(db_session):
    user = create_user(db_session, "expired@example.com")

    pending = asyncio.run(
        handle_message(db_session, user, "I spent ₹100 on snacks")
    )

    confirmation = (
        db_session.query(Confirmation)
        .filter_by(user_id=user.id)
        .one()
    )
    confirmation.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            handle_confirm(db_session, user, pending.confirmation_token)
        )

    assert exc.value.status_code == 409
    assert confirmation.status == "EXPIRED"
    assert db_session.query(Expense).filter_by(user_id=user.id).count() == 0
