from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.orchestrator import handle_confirm, handle_message
from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User
from app.schemas.agent import (
    AgentConfirmRequest,
    AgentMessageRequest,
    AgentMessageResponse,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/message", response_model=AgentMessageResponse)
async def post_message(
    payload: AgentMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentMessageResponse:
    return await handle_message(db, user, payload.text)


@router.post("/confirm", response_model=AgentMessageResponse)
async def post_confirm(
    payload: AgentConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AgentMessageResponse:
    return await handle_confirm(db, user, payload.confirmation_token)