from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import case

from app.models import Task
from app.schemas.task import TaskCreate
from app.tools.base import BaseTool, ToolContext, ToolResult


class ListTasksInput(BaseModel):
    include_completed: bool = False
    due_on: Optional[date] = None


class CompleteTaskInput(BaseModel):
    task_id: int = Field(ge=1)


class CreateTaskTool(BaseTool):
    name = "create_task"
    description = "Create a new task with an optional due date, priority and category."
    input_schema = TaskCreate
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: TaskCreate) -> ToolResult:
        task = Task(
            user_id=ctx.user.id,
            title=params.title,
            description=params.description,
            due_date=params.due_date,
            priority=params.priority.value,
            category=params.category,
        )
        ctx.db.add(task)
        ctx.db.commit()
        ctx.db.refresh(task)
        when = ""
        if task.due_date:
            when = f" due {task.due_date:%d %b %Y, %H:%M}"
        return ToolResult(
            success=True,
            message=f"Added task: {task.title}{when}.",
            data={"task_id": task.id},
        )

    def verify(self, ctx: ToolContext, params: TaskCreate, result: ToolResult) -> dict:
        task_id = (result.data or {}).get("task_id")
        saved = (ctx.db.query(Task).filter(Task.id == task_id, Task.user_id == ctx.user.id).one_or_none()
                 if task_id else None)
        expected_due = params.due_date
        actual_due = saved.due_date if saved else None
        if expected_due and actual_due:
            expected_due = expected_due.replace(tzinfo=None)
            actual_due = actual_due.replace(tzinfo=None)
        matches = bool(saved and saved.title == params.title
                       and (saved.description or None) == (params.description or None)
                       and saved.priority == params.priority.value
                       and (saved.category or None) == (params.category or None)
                       and actual_due == expected_due)
        return {"verified": matches, "method": "database_record_lookup",
                "evidence": {"task_id": task_id, "record_found": saved is not None,
                             "user_scope_checked": True, "fields_matched": matches}}


class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = "List tasks. Optionally filter to a specific day or include completed."
    input_schema = ListTasksInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ListTasksInput) -> ToolResult:
        query = ctx.db.query(Task).filter(Task.user_id == ctx.user.id)
        if not params.include_completed:
            query = query.filter(Task.completed.is_(False))
        if params.due_on is not None:
            start = datetime.combine(params.due_on, datetime.min.time())
            end = datetime.combine(params.due_on, datetime.max.time())
            query = query.filter(Task.due_date >= start, Task.due_date <= end)

        query = query.order_by(
            case((Task.due_date.is_(None), 1), else_=0),
            Task.due_date.asc(),
            Task.created_at.asc(),
        )
        tasks = query.all()

        if not tasks:
            return ToolResult(
                success=True,
                message="You have no tasks matching that filter.",
                data={"tasks": []},
            )
        lines = [f"- {'✓ ' if t.completed else ''}{t.title}" for t in tasks]
        return ToolResult(
            success=True,
            message="Here are your tasks:\n" + "\n".join(lines),
            data={
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "completed": t.completed,
                        "due_date": t.due_date.isoformat() if t.due_date else None,
                    }
                    for t in tasks
                ]
            },
        )


class CompleteTaskTool(BaseTool):
    name = "complete_task"
    description = "Mark a task as completed."
    input_schema = CompleteTaskInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: CompleteTaskInput) -> ToolResult:
        task = ctx.db.get(Task, params.task_id)
        if task is None or task.user_id != ctx.user.id:
            return ToolResult(success=False, message="Task not found.")
        if task.completed:
            return ToolResult(
                success=True,
                message=f"Task '{task.title}' is already completed.",
                data={"task_id": task.id},
            )
        task.completed = True
        task.completed_at = datetime.now(timezone.utc)
        ctx.db.commit()
        return ToolResult(
            success=True,
            message=f"Marked '{task.title}' as completed.",
            data={"task_id": task.id},
        )

    def verify(self, ctx: ToolContext, params: CompleteTaskInput, result: ToolResult) -> dict:
        saved = (ctx.db.query(Task).filter(Task.id == params.task_id, Task.user_id == ctx.user.id)
                 .one_or_none())
        verified = bool(saved and saved.completed and saved.completed_at is not None)
        return {"verified": verified, "method": "database_state_lookup",
                "evidence": {"task_id": params.task_id, "record_found": saved is not None,
                             "user_scope_checked": True, "completed": bool(saved and saved.completed),
                             "completed_at_present": bool(saved and saved.completed_at)}}
