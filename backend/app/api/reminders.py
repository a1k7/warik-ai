from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import Reminder, User
from app.schemas.reminder import ReminderCreate, ReminderResponse, ReminderUpdate

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
def create_reminder(
    payload: ReminderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReminderResponse:
    reminder = Reminder(
        user_id=user.id,
        title=payload.title,
        notes=payload.notes,
        remind_at=payload.remind_at,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return ReminderResponse.model_validate(reminder)


@router.get("/", response_model=list[ReminderResponse])
def list_reminders(
    upcoming_hours: Optional[int] = Query(default=None, ge=1, le=24 * 90),
    completed: Optional[bool] = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReminderResponse]:
    query = db.query(Reminder).filter(Reminder.user_id == user.id)
    
    if completed is not None:
        query = query.filter(Reminder.completed == completed)
        
    if upcoming_hours is not None:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=upcoming_hours)
        query = query.filter(Reminder.remind_at >= now, Reminder.remind_at <= cutoff)

    query = query.order_by(Reminder.remind_at.asc())
    reminders = query.all()
    return [ReminderResponse.model_validate(r) for r in reminders]


@router.put("/{reminder_id}", response_model=ReminderResponse)
def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReminderResponse:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise HTTPException(status_code=404, detail="Reminder not found")

    update_data = payload.model_dump(exclude_unset=True)
    
    if "completed" in update_data:
        if update_data["completed"] and not reminder.completed:
            reminder.completed_at = datetime.now(timezone.utc)
        elif not update_data["completed"]:
            reminder.completed_at = None

    for key, value in update_data.items():
        setattr(reminder, key, value)

    db.commit()
    db.refresh(reminder)
    return ReminderResponse.model_validate(reminder)


@router.post("/{reminder_id}/complete", response_model=ReminderResponse)
def complete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReminderResponse:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    if not reminder.completed:
        reminder.completed = True
        reminder.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(reminder)
        
    return ReminderResponse.model_validate(reminder)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    db.delete(reminder)
    db.commit()