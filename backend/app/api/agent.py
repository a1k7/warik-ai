
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.orchestrator import handle_confirm, handle_decline, handle_message
from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User, Conversation, Message
from app.schemas.agent import (
    AgentConfirmRequest,
    AgentMessageRequest,
    AgentMessageResponse,
)
from datetime import datetime
router = APIRouter(prefix="/agent", tags=["agent"])


def _update_confirmation_message(
    db: Session,
    user: User,
    token: str,
    status: str,
    *,
    content: str | None = None,
    result_data: dict | None = None,
) -> None:
    """Update the originating chat message without exposing tokens after use."""
    messages = (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.user_id == user.id,
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc())
        .limit(100)
        .all()
    )
    for message in messages:
        stored = dict(message.structured_data or {})
        metadata = stored.get("__confirmation")
        if not isinstance(metadata, dict) or metadata.get("confirmation_token") != token:
            continue

        metadata = dict(metadata)
        metadata["status"] = status
        metadata.pop("confirmation_token", None)
        stored.pop("__confirmation", None)

        if result_data:
            stored.update(result_data)
        if stored:
            stored["__confirmation"] = metadata
        else:
            stored = {"__confirmation": metadata}

        if content is not None:
            message.content = content
        message.structured_data = stored
        db.commit()
        return


@router.post("/message", response_model=AgentMessageResponse)
async def post_message(
    payload: AgentMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentMessageResponse:

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user.id,
            Conversation.is_archived.is_(False),
        )
        .order_by(Conversation.updated_at.desc())
        .first()
    )

    if not conv:
        conv = Conversation(user_id=user.id, title="New Chat")
        db.add(conv)
        db.commit()
        db.refresh(conv)

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=payload.text,
    )
    db.add(user_msg)

    if conv.title == "New Chat":
        words = payload.text.split()
        conv.title = " ".join(words[:5]) + ("..." if len(words) > 5 else "")

    db.commit()

    response = await handle_message(
        db,
        user,
        payload.text,
        conv,
        document_id=payload.document_id,
    )

    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=response.reply,
        structured_data=response.structured_data,
    )
    db.add(assistant_msg)

    conv.updated_at = datetime.utcnow()
    db.commit()

    response.conversation_id = conv.id
    return response


@router.post("/confirm", response_model=AgentMessageResponse)
async def post_confirm(
    payload: AgentConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentMessageResponse:
    response = await handle_confirm(
        db,
        user,
        payload.confirmation_token,
    )
    succeeded = bool(response.tool_calls) and all(
        call.success for call in response.tool_calls
    )
    _update_confirmation_message(
        db,
        user,
        payload.confirmation_token,
        "approved" if succeeded else "failed",
        content=response.reply,
        result_data=response.structured_data,
    )
    return response


@router.post("/decline")
async def post_decline(
    payload: AgentConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    response = await handle_decline(
        db,
        user,
        payload.confirmation_token,
    )
    _update_confirmation_message(
        db,
        user,
        payload.confirmation_token,
        "declined",
    )
    return response
