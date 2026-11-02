"""The agent pipeline:

1. Accept user text.
2. Try the deterministic parser.
3. Fall back to the LLM provider.
4. Validate the extracted arguments against the tool's Pydantic schema.
5. Return a confirmation card if the tool requires it.
6. Otherwise execute via the registry (which writes an audit log) and reply.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents import deterministic_parser
from app.agents.llm_provider import get_provider
from app.core.config import settings
from app.models import User
from app.schemas.agent import AgentMessageResponse, ToolCallInfo
from app.tools.base import ToolContext
from app.tools.registry import registry

_FALLBACK_HINT = (
    "I can help with tasks, reminders, expenses, travel planning and memories. "
    "Try: 'Add a task to buy groceries', 'Remind me to study at 7 PM', "
    "'I spent ₹250 on lunch', or 'How much did I spend this week?'"
)


def _make_confirmation_token(user_id: int, tool_name: str, params: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "confirm",
        "user_id": user_id,
        "tool_name": tool_name,
        "params": params,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_confirmation_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token")
    if payload.get("purpose") != "confirm":
        raise HTTPException(status_code=400, detail="Token is not a confirmation token")
    return payload


def _validate_and_maybe_confirm(
    db: Session,
    user: User,
    tool_name: str,
    raw_params: dict,
    tool,
) -> AgentMessageResponse:
    try:
        params_model = tool.input_schema(**raw_params)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][0] if first["loc"] else "argument"
        return AgentMessageResponse(reply=f"I need a bit more info — {field}: {first['msg']}.")

    if tool.requires_confirmation:
        args = params_model.model_dump(mode="json")
        token = _make_confirmation_token(user.id, tool.name, args)
        return AgentMessageResponse(
            reply=f"Should I {tool.confirmation_prompt(params_model)}?",
            needs_confirmation=True,
            confirmation_token=token,
            pending_tool=tool.name,
            pending_args=args,
        )

    ctx = ToolContext(db=db, user=user)
    result = registry.dispatch(ctx, tool.name, raw_params)
    return AgentMessageResponse(
        reply=result.message,
        tool_calls=[
            ToolCallInfo(
                tool_name=tool.name,
                args=raw_params,
                success=result.success,
                message=result.message,
            )
        ],
    )


async def handle_message(db: Session, user: User, text: str) -> AgentMessageResponse:
    text = (text or "").strip()
    if not text:
        return AgentMessageResponse(reply="Please say something so I can help.")

    route: Optional[dict] = deterministic_parser.parse(text)
    if route is None:
        route = await get_provider().route(text)

    if route is None:
        return AgentMessageResponse(reply=_FALLBACK_HINT)

    intent = str(route.get("intent", "chat"))
    params = route.get("params") or {}

    if intent == "chat":
        reply = params.get("reply") or "Tell me more."
        return AgentMessageResponse(reply=str(reply))

    tool = registry.get(intent)
    if tool is None:
        return AgentMessageResponse(reply=f"I don't know how to do '{intent}' yet.")

    return _validate_and_maybe_confirm(db, user, intent, params, tool)


async def handle_confirm(db: Session, user: User, token: str) -> AgentMessageResponse:
    payload = _decode_confirmation_token(token)
    if payload.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Confirmation token belongs to another user")

    tool_name = payload.get("tool_name")
    params = payload.get("params") or {}
    tool = registry.get(tool_name) if tool_name else None
    if tool is None:
        raise HTTPException(status_code=400, detail="Unknown tool in confirmation token")

    ctx = ToolContext(db=db, user=user)
    result = registry.dispatch(ctx, tool_name, params)
    return AgentMessageResponse(
        reply=result.message,
        tool_calls=[
            ToolCallInfo(
                tool_name=tool_name,
                args=params,
                success=result.success,
                message=result.message,
            )
        ],
    )