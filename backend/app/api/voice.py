import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.agents.orchestrator import handle_message
from app.api.deps import get_current_user
from app.core.config import settings
from app.database.session import get_db
from app.models import User
from app.schemas.voice import TranscriptionResponse, TTSRequest, VoiceMessageResponse
from app.services.audio_probe import estimate_duration_seconds
from app.services.gnani_stt import GnaniSTTError
from app.services.gnani_tts import GnaniTTSError
from app.services.stt_provider import (
    STTNotConfiguredError,
    STTProvider,
    SUPPORTED_STT_LANGUAGES,
    get_stt_provider,
)
from app.models import User, Conversation, Message
from datetime import datetime
from app.services.tts_provider import (
    TTSNotConfiguredError,
    TTSProvider,
    get_tts_provider,
)
from app.services.voice_usage import (
    VoiceUsageLimitError,
    check_stt_limit,
    check_tts_limit,
    increment_stt,
    increment_tts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/ogg", "audio/mp4", "audio/m4a", "audio/x-m4a",
    "audio/webm", "video/webm", "application/octet-stream",
}


async def _read_with_limit(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large. Limit: {max_bytes} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_language(language_code: str) -> str:
    code = (language_code or "").strip()
    if code not in SUPPORTED_STT_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language_code '{language_code}'. Supported: {sorted(SUPPORTED_STT_LANGUAGES)}",
        )
    return code


async def _transcribe_or_raise(
    *,
    audio: UploadFile,
    language_code: str,
    duration_seconds: Optional[float],
    provider: STTProvider,
    db: Session,
    user: User,
) -> tuple[str, Optional[str], int, int]:
    if not settings.voice_enabled:
        raise HTTPException(
            status_code=503,
            detail="Voice is disabled. Set VOICE_ENABLED=true in backend/.env to enable.",
        )

    code = _validate_language(language_code)

    # STT can use Groq or Gnani. Do not require a Gnani key when Groq is the
    # selected provider, and never report a configured service when neither is.
    has_gnani_key = bool(settings.gnani_api_key and settings.gnani_api_key.strip())
    has_groq_key = bool(settings.groq_api_key and settings.groq_api_key.strip())
    if not (has_gnani_key or has_groq_key):
        raise HTTPException(
            status_code=503,
            detail="Neither GROQ_API_KEY nor GNANI_API_KEY is configured. Speech-to-text service is not configured.",
        )

    if audio.content_type and audio.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio content type: {audio.content_type}",
        )

    audio_bytes = await _read_with_limit(audio, settings.voice_max_upload_bytes)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    requested = (
        int(round(duration_seconds))
        if duration_seconds and duration_seconds > 0
        else settings.voice_max_duration_seconds
    )

    try:
        check_stt_limit(db, user, requested)
    except VoiceUsageLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    try:
        result = await provider.transcribe(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio",
            content_type=audio.content_type,
            language_code=code,
        )
    except STTNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except GnaniSTTError as exc:
        raise HTTPException(status_code=502, detail=f"STT failed: {exc}")
    except Exception as exc:
        # This logs the EXACT traceback to your terminal
        logger.error("Unexpected STT error", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected STT error: {str(exc)}")

    actual_seconds = (
        int(round(duration_seconds))
        if duration_seconds and duration_seconds > 0
        else estimate_duration_seconds(audio_bytes, audio.content_type, settings.voice_max_duration_seconds)
    )
    usage = increment_stt(db, user, actual_seconds)

    return result.transcript, result.request_id, usage.seconds_used, settings.voice_usage_limit_seconds


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    audio: UploadFile = File(...),
    language_code: str = Form("en-IN"),
    duration_seconds: Optional[float] = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    provider: STTProvider = Depends(get_stt_provider),
) -> TranscriptionResponse:
    transcript, request_id, used, limit = await _transcribe_or_raise(
        audio=audio, language_code=language_code, duration_seconds=duration_seconds,
        provider=provider, db=db, user=user,
    )
    return TranscriptionResponse(
        transcript=transcript, request_id=request_id, language_code=language_code,
        usage_seconds_used=used, usage_seconds_limit=limit,
    )


@router.post("/message", response_model=VoiceMessageResponse)
async def voice_message(
    audio: UploadFile = File(...),
    language_code: str = Form("en-IN"),
    duration_seconds: Optional[float] = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    provider: STTProvider = Depends(get_stt_provider),
) -> VoiceMessageResponse:
    transcript, _request_id, _used, _limit = await _transcribe_or_raise(
        audio=audio, language_code=language_code, duration_seconds=duration_seconds,
        provider=provider, db=db, user=user,
    )
    
        # Reuse the user's latest active conversation.
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user.id,
            Conversation.is_archived.is_(False),
        )
        .order_by(Conversation.updated_at.desc())
        .first()
    )

    if not conversation:
        conversation = Conversation(
            user_id=user.id,
            title="New Chat",
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=transcript,
        )
    )
    db.commit()

    agent_response = await handle_message(
        db,
        user,
        transcript,
        conversation,
    )

    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=agent_response.reply,
            structured_data=agent_response.structured_data,
        )
    )

    conversation.updated_at = datetime.utcnow()
    db.commit()

    agent_response.conversation_id = conversation.id
    
    return VoiceMessageResponse(
        transcript=transcript,
        reply=agent_response.reply,
        tool_calls=agent_response.tool_calls,
        needs_confirmation=agent_response.needs_confirmation,
        confirmation_token=agent_response.confirmation_token,
        pending_tool=agent_response.pending_tool,
        pending_args=agent_response.pending_args,
    )


@router.post("/speak")
async def speak(
    payload: TTSRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    provider: TTSProvider = Depends(get_tts_provider),
) -> Response:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    
    requested_chars = len(text)

    try:
        check_tts_limit(db, user, requested_chars)
    except VoiceUsageLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    try:
        audio_bytes, was_cached = await provider.synthesize(text, payload.language_code)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except GnaniTTSError as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}")
    except Exception as exc:
        logger.error("Unexpected TTS error", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected TTS error: {str(exc)}")

    if not was_cached:
        increment_tts(db, user, requested_chars)

    return Response(content=audio_bytes, media_type="audio/wav")