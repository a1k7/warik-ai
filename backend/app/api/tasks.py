from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import Task, User
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    task = Task(
        user_id=user.id,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        priority=payload.priority.value,
        category=payload.category,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.get("/", response_model=list[TaskResponse])
def list_tasks(
    completed: Optional[bool] = Query(default=None),
    due_before: Optional[datetime] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    query = db.query(Task).filter(Task.user_id == user.id)
    
    if completed is not None:
        query = query.filter(Task.completed == completed)
    if due_before is not None:
        query = query.filter(Task.due_date <= due_before)
    if category is not None:
        query = query.filter(Task.category == category)
        
    # Order by due date (nulls last), then priority (high to low), then created_at
    query = query.order_by(
        case((Task.due_date.is_(None), 1), else_=0),
        Task.due_date.asc(),
        Task.created_at.desc(),
    )
    
    tasks = query.all()
    return [TaskResponse.model_validate(t) for t in tasks]


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = payload.model_dump(exclude_unset=True)
    
    if "completed" in update_data:
        if update_data["completed"] and not task.completed:
            task.completed_at = datetime.now(timezone.utc)
        elif not update_data["completed"]:
            task.completed_at = None
            
    if "priority" in update_data and update_data["priority"] is not None:
        update_data["priority"] = update_data["priority"].value

    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not task.completed:
        task.completed = True
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)
        
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db.delete(task)
    db.commit()