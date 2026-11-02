"""Per-user, per-day voice usage tracking.

Design:
- `check_*` methods NEVER write to the DB. If rejected, no footprint.
- `increment_*` methods are only called after a successful provider response.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import User, VoiceUsage


class VoiceUsageLimitError(Exception):
    def __init__(self, resource: str, used: int, limit: int) -> None:
        self.resource = resource
        self.used = used
        self.limit = limit
        super().__init__(
            f"Voice {resource} limit reached for today: {used}/{limit}. "
            "Try again tomorrow or raise the limit in backend/.env."
        )


def _today() -> date:
    return date.today()


def _today_usage(db: Session, user: User) -> Optional[VoiceUsage]:
    return (
        db.query(VoiceUsage)
        .filter(VoiceUsage.user_id == user.id, VoiceUsage.usage_date == _today())
        .first()
    )


def check_stt_limit(db: Session, user: User, requested_seconds: int) -> None:
    cap = settings.voice_usage_limit_seconds
    usage = _today_usage(db, user)
    used = usage.seconds_used if usage else 0
    if used + max(0, requested_seconds) > cap:
        raise VoiceUsageLimitError("STT", used=used, limit=cap)


def check_tts_limit(db: Session, user: User, requested_chars: int) -> None:
    cap = settings.voice_tts_char_limit
    usage = _today_usage(db, user)
    used = usage.characters_used if usage else 0
    if used + max(0, requested_chars) > cap:
        raise VoiceUsageLimitError("TTS", used=used, limit=cap)


def _get_or_create_today(db: Session, user: User) -> VoiceUsage:
    usage = _today_usage(db, user)
    if usage is None:
        usage = VoiceUsage(
            user_id=user.id,
            usage_date=_today(),
            seconds_used=0,
            requests_count=0,
            characters_used=0,
            tts_requests_count=0,
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)
    return usage


def increment_stt(db: Session, user: User, seconds: int) -> VoiceUsage:
    usage = _get_or_create_today(db, user)
    usage.seconds_used += max(1, int(round(seconds)))
    usage.requests_count += 1
    usage.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(usage)
    return usage


def increment_tts(db: Session, user: User, characters: int) -> VoiceUsage:
    usage = _get_or_create_today(db, user)
    usage.characters_used += max(1, characters)
    usage.tts_requests_count += 1
    usage.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(usage)
    return usage