"""User-scoped Action Ledger API."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User
from app.models.commitment import Commitment
from app.schemas.commitment import CommitmentCreate, CommitmentResponse, CommitmentUpdate

router = APIRouter(prefix="/commitments", tags=["action-ledger"])
VALID_STATUSES = {"open", "in_progress", "waiting", "blocked", "completed"}


def _owned(db: Session, commitment_id: int, user: User) -> Commitment:
    item = db.get(Commitment, commitment_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return item


@router.post("/", response_model=CommitmentResponse, status_code=status.HTTP_201_CREATED)
def create_commitment(
    payload: CommitmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = Commitment(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/", response_model=list[CommitmentResponse])
def list_commitments(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Commitment).filter(Commitment.user_id == user.id)
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid commitment status")
        query = query.filter(Commitment.status == status_filter)
    return query.order_by(Commitment.due_at.asc(), Commitment.created_at.desc()).all()


@router.patch("/{commitment_id}", response_model=CommitmentResponse)
def update_commitment(
    commitment_id: int,
    payload: CommitmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _owned(db, commitment_id, user)
    changes = payload.model_dump(exclude_unset=True)
    new_status = changes.get("status")
    if new_status == "completed":
        note = changes.get("verification_note") or item.verification_note
        if not note or len(note.strip()) < 3:
            raise HTTPException(
                status_code=422,
                detail="Add a short verification note before marking this commitment complete.",
            )
        item.verified_at = datetime.now(timezone.utc)
    elif new_status and new_status != "completed":
        item.verified_at = None
        item.verification_note = None
    for key, value in changes.items():
        setattr(item, key, value.value if key == "status" and value else value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{commitment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commitment(
    commitment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _owned(db, commitment_id, user)
    db.delete(item)
    db.commit()
