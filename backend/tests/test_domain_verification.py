from datetime import datetime, timedelta, timezone
import json

from app.core.security import hash_password
from app.models import Reminder, SavedTrip, Task, TravelPlan, User
from app.schemas.reminder import ReminderCreate
from app.schemas.task import TaskCreate, TaskPriority
from app.schemas.travel import TravelPlanCreate, TravelStopCreate
from app.tools.base import ToolContext
from app.tools.reminders import CreateReminderTool
from app.tools.tasks import CompleteTaskInput, CompleteTaskTool, CreateTaskTool
from app.tools.travel import CreateTravelPlanTool
from app.tools.trip_tools import SaveTripInput, SaveTripTool


def make_user(db, email="verify@example.com"):
    user = User(email=email, name="Verifier", password_hash=hash_password("password123"))
    db.add(user); db.commit(); db.refresh(user)
    return user


def test_create_task_verifies_persisted_fields_and_user_scope(db_session):
    user = make_user(db_session); ctx = ToolContext(db_session, user)
    params = TaskCreate(title="Submit report", priority=TaskPriority.HIGH, category="work")
    tool = CreateTaskTool(); result = tool.execute(ctx, params)
    assert tool.verify(ctx, params, result)["verified"] is True
    other = make_user(db_session, "other@example.com")
    assert db_session.query(Task).filter(Task.user_id == other.id).count() == 0


def test_complete_task_verifies_completed_state(db_session):
    user = make_user(db_session); ctx = ToolContext(db_session, user)
    task = Task(user_id=user.id, title="Finish assignment", completed=False)
    db_session.add(task); db_session.commit()
    tool = CompleteTaskTool(); params = CompleteTaskInput(task_id=task.id)
    result = tool.execute(ctx, params)
    evidence = tool.verify(ctx, params, result)
    assert evidence["verified"] is True
    assert evidence["evidence"]["completed_at_present"] is True


def test_create_reminder_verifies_persisted_datetime(db_session):
    user = make_user(db_session); ctx = ToolContext(db_session, user)
    params = ReminderCreate(title="Call dentist", notes="Ask about appointment",
                            remind_at=datetime.now(timezone.utc) + timedelta(days=1))
    tool = CreateReminderTool(); result = tool.execute(ctx, params)
    assert tool.verify(ctx, params, result)["verified"] is True


def test_create_travel_plan_verifies_plan_and_stops(db_session):
    user = make_user(db_session); ctx = ToolContext(db_session, user)
    params = TravelPlanCreate(title="Japan trip", origin="Mumbai", destination="Tokyo",
        travellers=2, currency="INR", stops=[TravelStopCreate(name="Senso-ji", notes="Visit temple")])
    tool = CreateTravelPlanTool(); result = tool.execute(ctx, params)
    evidence = tool.verify(ctx, params, result)
    assert evidence["verified"] is True
    assert evidence["evidence"]["stop_count"] == 1


def test_save_trip_returns_id_and_verifies_exact_itinerary(db_session):
    user = make_user(db_session); ctx = ToolContext(db_session, user)
    itinerary = {"days": [{"day": 1, "activities": ["Museum"]}]}
    params = SaveTripInput(destination="Tokyo", days=1, itinerary_json=json.dumps(itinerary))
    tool = SaveTripTool(); result = tool.execute(ctx, params)
    assert result.data["saved_trip_id"]
    assert tool.verify(ctx, params, result)["verified"] is True
    assert db_session.query(SavedTrip).filter(SavedTrip.user_id == user.id).count() == 1
