from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User, Conversation, Message
from app.schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationResponse,
    ConversationDetailResponse
)
from app.agents.orchestrator import handle_message
from app.schemas.agent import AgentMessageRequest

router = APIRouter(prefix="/conversations", tags=["conversations"])

@router.get("", response_model=List[ConversationResponse])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    convs = db.query(Conversation).filter(
        Conversation.user_id == user.id,
        Conversation.is_archived == False
    ).order_by(Conversation.updated_at.desc()).all()
    return convs

@router.post("", response_model=ConversationResponse)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    conv = Conversation(user_id=user.id, title=payload.title or "New Chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

@router.get("/{conv_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv

@router.patch("/{conv_id}", response_model=ConversationResponse)
def update_conversation(
    conv_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if payload.title is not None:
        conv.title = payload.title
    if payload.is_archived is not None:
        conv.is_archived = payload.is_archived

    db.commit()
    db.refresh(conv)
    return conv

@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conv)
    db.commit()
    return {"status": "deleted"}

@router.post("/{conv_id}/message")
async def send_message(
    conv_id: int,
    payload: AgentMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id, Conversation.user_id == user.id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_msg = Message(conversation_id=conv.id, role="user", content=payload.text)
    db.add(user_msg)

    if conv.title == "New Chat" and len(conv.messages) <= 1:
        words = payload.text.split()
        conv.title = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
    db.commit()

    # NEW: pass document_id
    agent_response = await handle_message(
        db, user, payload.text, conv, document_id=payload.document_id
    )

    assistant_msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=agent_response.reply,
        structured_data=agent_response.structured_data,
    )
    db.add(assistant_msg)
    conv.updated_at = datetime.utcnow()
    db.commit()

    return agent_response
