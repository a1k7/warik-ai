from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.models.confirmation import Confirmation
from app.models.action_log import ActionLog

def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def create_confirmation(db: Session, *, user_id: int, tool_name: str, params: dict, expires_at: datetime) -> Confirmation:
    record = Confirmation(jti=str(uuid4()), user_id=user_id, tool_name=tool_name, params=params, status="PENDING", expires_at=expires_at.astimezone(timezone.utc).replace(tzinfo=None))
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

def consume_confirmation(db: Session, *, jti: str, user_id: int) -> tuple[Confirmation | None, str | None]:
    now = _now_utc_naive()
    result = db.execute(update(Confirmation).where(Confirmation.jti == jti, Confirmation.user_id == user_id, Confirmation.status == "PENDING", Confirmation.expires_at > now).values(status="APPROVED", consumed_at=now))
    db.commit()
    if result.rowcount == 1:
        record = db.query(Confirmation).filter(Confirmation.jti == jti, Confirmation.user_id == user_id).one()
        db.add(ActionLog(user_id=user_id, action="confirmation.approved", tool_name=record.tool_name, payload={"confirmation_id": record.id, "jti": record.jti}, result_status="success", result_message="User approval accepted; confirmation consumed."))
        db.commit()
        return record, None
    record = db.query(Confirmation).filter(Confirmation.jti == jti, Confirmation.user_id == user_id).one_or_none()
    if record is None:
        return None, "Invalid confirmation."
    if record.status == "PENDING" and record.expires_at <= now:
        record.status = "EXPIRED"
        db.commit()
        return None, "Confirmation token expired."
    return None, "Confirmation has already been used or is no longer pending."

def finalize_confirmation(db: Session, *, confirmation_id: int, user_id: int, success: bool, message: str) -> None:
    record = db.query(Confirmation).filter(Confirmation.id == confirmation_id, Confirmation.user_id == user_id, Confirmation.status == "APPROVED").one_or_none()
    if record is None:
        raise RuntimeError("Claimed confirmation could not be finalized.")
    record.status = "EXECUTED" if success else "FAILED"
    db.add(ActionLog(user_id=user_id, action="confirmation.executed" if success else "confirmation.execution_failed", tool_name=record.tool_name, payload={"confirmation_id": record.id, "jti": record.jti}, result_status="success" if success else "failed", result_message=(message or "")[:1000]))
    db.commit()
