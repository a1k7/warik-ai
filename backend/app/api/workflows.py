from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User, Workflow
from app.schemas.workflow import WorkflowResponse
from app.agents.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/workflows", tags=["workflows"])


class RejectStepRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


def _owned_workflow(db: Session, workflow_id: int, user: User) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.user_id != user.id:
        # Do not disclose whether another user's workflow exists.
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wf = _owned_workflow(db, workflow_id, user)
    return WorkflowResponse(
        id=wf.id,
        goal_id=wf.goal_id,
        status=wf.status,
        steps=wf.steps_json or [],
        created_at=wf.created_at,
    )


@router.post("/{workflow_id}/approve/{step_id}")
def approve_step(
    workflow_id: int,
    step_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wf = _owned_workflow(db, workflow_id, user)
    engine = WorkflowEngine(db, user)
    if not engine.approve_step(wf, step_id):
        raise HTTPException(
            status_code=409,
            detail="Step is not awaiting approval, or its state changed. Refresh the workflow.",
        )

    # execute() claims the APPROVED -> EXECUTING transition before invoking the tool.
    execution = engine.execute(wf)
    return {
        "workflow_id": wf.id,
        "status": wf.status,
        "steps": wf.steps_json or [],
        "executed": execution["executed"],
        "awaiting_approval": execution["awaiting_approval"],
    }


@router.post("/{workflow_id}/reject/{step_id}")
def reject_step(
    workflow_id: int,
    step_id: str,
    payload: RejectStepRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wf = _owned_workflow(db, workflow_id, user)
    engine = WorkflowEngine(db, user)
    reason = payload.reason if payload else None
    if not engine.reject_step(wf, step_id, reason):
        raise HTTPException(
            status_code=409,
            detail="Step is not awaiting approval, or its state changed. Refresh the workflow.",
        )

    # Rejection is terminal for this step; do not execute it or downstream steps here.
    return {
        "workflow_id": wf.id,
        "status": wf.status,
        "steps": wf.steps_json or [],
        "rejected_step_id": step_id,
    }


@router.post("/{workflow_id}/retry/{step_id}")
def retry_step(
    workflow_id: int,
    step_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    wf = _owned_workflow(db, workflow_id, user)
    engine = WorkflowEngine(db, user)
    result = engine.retry_step(wf, step_id)
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=result["reason"])

    # Immediately execute the retried step + any newly-unblocked downstream steps.
    exec_result = engine.execute(wf)
    return {
        "workflow_id": wf.id,
        "status": wf.status,
        "steps": wf.steps_json or [],
        "executed": exec_result["executed"],
    }
