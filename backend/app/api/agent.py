
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.orchestrator import handle_confirm, handle_message
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
    return await handle_confirm(
        db,
        user,
        payload.confirmation_token,
    )
