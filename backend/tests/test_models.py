from datetime import date, datetime
from decimal import Decimal

from app.core.security import hash_password
from app.models import Expense, Reminder, Task, TravelPlan, TravelStop, User, UserPreference


def _new_user(db, email: str) -> User:
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_user_preference_relationship(db_session):
    user = _new_user(db_session, "a@example.com")
    pref = UserPreference(user_id=user.id)
    db_session.add(pref)
    db_session.commit()
    db_session.refresh(user)

    assert user.preference is not None
    assert user.preference.preferred_language == "en-IN"
    assert user.preference.default_currency == "INR"
    assert user.preference.voice_responses_enabled is False


def test_task_ownership(db_session):
    user = _new_user(db_session, "b@example.com")
    task = Task(user_id=user.id, title="Buy groceries")
    db_session.add(task)
    db_session.commit()

    stored = db_session.query(Task).filter(Task.user_id == user.id).one()
    assert stored.title == "Buy groceries"
    assert stored.completed is False
    assert stored.priority == "medium"


def test_expense_amount_is_decimal(db_session):
    user = _new_user(db_session, "c@example.com")
    expense = Expense(
        user_id=user.id,
        amount=Decimal("250.50"),
        category="Food",
        description="Lunch",
        expense_date=date.today(),
    )
    db_session.add(expense)
    db_session.commit()

    stored = db_session.query(Expense).one()
    assert stored.amount == Decimal("250.50")
    assert isinstance(stored.amount, Decimal)


def test_reminder_time_roundtrip(db_session):
    user = _new_user(db_session, "d@example.com")
    remind_at = datetime(2026, 6, 1, 19, 0, 0)
    reminder = Reminder(user_id=user.id, title="Study", remind_at=remind_at)
    db_session.add(reminder)
    db_session.commit()

    stored = db_session.query(Reminder).one()
    assert stored.remind_at.year == 2026
    assert stored.remind_at.hour == 19


def test_travel_plan_with_stops(db_session):
    user = _new_user(db_session, "e@example.com")
    plan = TravelPlan(
        user_id=user.id,
        title="Bhopal to Indore",
        origin="Bhopal",
        destination="Indore",
        travellers=2,
        budget=Decimal("2000.00"),
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    stop_a = TravelStop(travel_plan_id=plan.id, order_index=0, name="Bhopal Junction")
    stop_b = TravelStop(travel_plan_id=plan.id, order_index=1, name="Indore Junction")
    db_session.add_all([stop_a, stop_b])
    db_session.commit()
    db_session.refresh(plan)

    names = [s.name for s in plan.stops]
    assert names == ["Bhopal Junction", "Indore Junction"]