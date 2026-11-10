from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import case

from app.models import Reminder
from app.schemas.reminder import ReminderCreate
from app.tools.base import BaseTool, ToolContext, ToolResult


class ListRemindersInput(BaseModel):
    upcoming_hours: int = Field(default=24, ge=1, le=24 * 90)


class CreateReminderTool(BaseTool):
    name = "create_reminder"
    description = "Create a reminder for a specific date and time."
    input_schema = ReminderCreate
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ReminderCreate) -> ToolResult:
        reminder = Reminder(
            user_id=ctx.user.id,
            title=params.title,
            notes=params.notes,
            remind_at=params.remind_at,
        )
        ctx.db.add(reminder)
        ctx.db.commit()
        ctx.db.refresh(reminder)
        return ToolResult(
            success=True,
            message=f"Reminder set: {reminder.title} — {reminder.remind_at:%d %b %Y, %H:%M}.",
            data={"reminder_id": reminder.id},
        )

    def verify(self, ctx: ToolContext, params: ReminderCreate, result: ToolResult) -> dict:
        reminder_id = (result.data or {}).get("reminder_id")
        saved = (ctx.db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == ctx.user.id)
                 .one_or_none() if reminder_id else None)
        expected_at = params.remind_at.replace(tzinfo=None)
        actual_at = saved.remind_at.replace(tzinfo=None) if saved else None
        matches = bool(saved and saved.title == params.title
                       and (saved.notes or None) == (params.notes or None)
                       and actual_at == expected_at)
        return {"verified": matches, "method": "database_record_lookup",
                "evidence": {"reminder_id": reminder_id, "record_found": saved is not None,
                             "user_scope_checked": True, "fields_matched": matches}}


class ListRemindersTool(BaseTool):
    name = "list_reminders"
    description = "List upcoming reminders within the next N hours (default 24)."
    input_schema = ListRemindersInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ListRemindersInput) -> ToolResult:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=params.upcoming_hours)
        reminders = (
            ctx.db.query(Reminder)
            .filter(
                Reminder.user_id == ctx.user.id,
                Reminder.completed.is_(False),
                Reminder.remind_at >= now,
                Reminder.remind_at <= cutoff,
            )
            .order_by(Reminder.remind_at.asc())
            .all()
        )
        if not reminders:
            return ToolResult(
                success=True,
                message=f"No reminders in the next {params.upcoming_hours} hours.",
                data={"reminders": []},
            )
        lines = [f"- {r.title} — {r.remind_at:%d %b %H:%M}" for r in reminders]
        return ToolResult(
            success=True,
            message="Upcoming reminders:\n" + "\n".join(lines),
            data={
                "reminders": [
                    {"id": r.id, "title": r.title, "remind_at": r.remind_at.isoformat()}
                    for r in reminders
                ]
            },
        )
