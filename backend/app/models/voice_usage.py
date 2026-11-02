from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class VoiceUsage(Base):
    """Per-user, per-day voice usage ledger for both STT and TTS."""

    __tablename__ = "voice_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_voice_usage_user_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # STT usage
    seconds_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # TTS usage
    characters_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tts_requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )