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



@router.get("/briefing")
def get_commitment_briefing(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return deterministic attention signals from the user's open commitments."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    local_tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(local_tz)
    horizon = now + timedelta(hours=48)
    items = (
        db.query(Commitment)
        .filter(Commitment.user_id == user.id, Commitment.status != "completed")
        .order_by(Commitment.due_at.asc(), Commitment.created_at.asc())
        .all()
    )

    attention = []
    counts = {
        "active": len(items),
        "overdue": 0,
        "due_today": 0,
        "due_soon": 0,
        "waiting": 0,
        "blocked": 0,
    }

    for item in items:
        signals = []
        due = item.due_at
        if due is not None:
            if due.tzinfo is None:
                # SQLite may return naive timestamps; commitment deadlines are
                # entered in the app's configured India timezone.
                due = due.replace(tzinfo=local_tz)
            else:
                due = due.astimezone(local_tz)

            if due < now:
                signals.append("overdue")
                counts["overdue"] += 1
            elif due.date() == now.date():
                signals.append("due_today")
                counts["due_today"] += 1
            elif due <= horizon:
                signals.append("due_soon")
                counts["due_soon"] += 1

        if item.status == "waiting":
            signals.append("waiting")
            counts["waiting"] += 1
        elif item.status == "blocked":
            signals.append("blocked")
            counts["blocked"] += 1

        if not signals:
            continue

        if item.status == "waiting" and item.counterparty:
            next_step = f"Follow up with {item.counterparty} about this commitment."
        elif item.status == "blocked":
            next_step = "Identify and resolve the blocker before the deadline."
        elif "overdue" in signals:
            next_step = "Review the delay and set a realistic next date."
        elif "due_today" in signals:
            next_step = "Give this commitment attention today."
        else:
            next_step = "Move this commitment forward before it becomes urgent."

        attention.append({
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "counterparty": item.counterparty,
            "due_at": due.isoformat() if due else None,
            "signals": signals,
            "suggested_next_step": next_step,
        })

    priority = {"overdue": 0, "blocked": 1, "due_today": 2, "waiting": 3, "due_soon": 4}
    attention.sort(
        key=lambda entry: min(priority.get(signal, 9) for signal in entry["signals"])
    )
    attention = attention[:8]

    signal_total = sum(counts[key] for key in ("overdue", "due_today", "due_soon", "waiting", "blocked"))
    if not items:
        headline = "Your Action Ledger is clear. Capture a commitment when something needs follow-through."
    elif not attention:
        headline = "No commitments need immediate attention. Keep moving your active work forward."
    else:
        headline = f"{len(attention)} commitment(s) need attention. Start with the highest-priority signal below."

    return {
        "generated_at": now.isoformat(),
        "timezone": "Asia/Kolkata",
        "headline": headline,
        "counts": counts,
        "attention_items": attention,
        "has_attention": bool(attention),
        "signal_count": signal_total,
    }
