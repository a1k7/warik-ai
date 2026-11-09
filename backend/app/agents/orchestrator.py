
"""Warik AI orchestrator — strict routing, no state leaks."""

from datetime import datetime, timedelta, timezone
import re
import jwt
import logging

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.llm_provider import get_provider
from app.agents.goal_interpreter import GoalInterpreter
from app.agents.universal_planner import UniversalTaskPlanner
from app.agents.workflow_engine import WorkflowEngine
from app.agents.deterministic_parser import (
    _normalize_people,
    _extract_budget,
    parse as parse_deterministic,
)
from app.core.config import settings
from app.models import User, Conversation, Workflow
from app.schemas.agent import AgentMessageResponse, ToolCallInfo
from app.tools.base import ToolContext
from app.tools.registry import registry
from app.services.confirmation_service import create_confirmation, consume_confirmation, finalize_confirmation


logger = logging.getLogger(__name__)


# ─── PATTERNS ──────────────────────────────────────────────

FINANCIAL_PATTERNS = [
    r"\bsalary\b.*\b(?:rent|food|travel|savings|budget)\b",
    r"\b(?:savings?|budget|monthly)\s*plan\b",
]

TRAVEL_PATTERNS = [
    r"\b(?:plan|make|create|build)\b.*\b(?:trip|itinerary|vacation|holiday|getaway|weekend break)\b",
    r"\bweekend\s+(?:trip|getaway|break)\b",
    r"\b\d+[- ]day\b.*\b(?:trip|itinerary|getaway)\b",
]

FOOD_PATTERNS = [
    r"\b(?:find|show|recommend|suggest|good|best|cheap)\b.*\b(?:restaurant|food|cafe|eat|dinner|lunch|breakfast)\b",
    r"\b(?:hungry|what should i eat|where.*eat)\b",
    r"\b(?:biryani|pizza|burger|momos|dosa|idli|chinese|thali|paneer|chicken|shawarma|kebab)\b",
]

HOTEL_PATTERNS = [
    r"\b(?:find|show|book|search|need|want)\b.*\b(?:hotel|stay|accommodation|room)\b",
    r"\bhotel\b.*\b(?:in|near|at)\b",
]


# ─── COMPREHENSIVE KNOWN CITIES ─────────────────────────────

KNOWN_CITY_NAMES = {
    "delhi", "new delhi", "mumbai", "bombay", "bangalore", "bengaluru",
    "chennai", "kolkata", "hyderabad", "pune", "jaipur", "goa", "panaji",
    "kochi", "cochin", "ahmedabad", "lucknow", "agra", "varanasi", "amritsar",
    "udaipur", "jodhpur", "jaisalmer", "shimla", "manali", "dharamshala",
    "darjeeling", "munnar", "alleppey", "alappuzha", "trivandrum", "wayanad",
    "bhopal", "indore", "nagpur", "surat", "vadodara", "coimbatore",
}


# ─── STATE ↔ CITIES (FOR MISMATCH DETECTION) ────────────────

STATE_KEYWORDS = {
    "west bengal": ["kolkata", "darjeeling", "siliguri", "sundarbans"],
    "kerala": [
        "kochi", "cochin", "munnar", "alleppey", "alappuzha",
        "wayanad", "varkala", "kumarakom", "trivandrum", "thekkady",
    ],
    "rajasthan": ["jaipur", "udaipur", "jodhpur", "jaisalmer", "ajmer"],
    "maharashtra": ["mumbai", "pune", "nashik", "nagpur"],
    "goa": ["panaji", "calangute", "margao"],
    "punjab": ["amritsar", "chandigarh", "ludhiana"],
    "tamil nadu": ["chennai", "coimbatore", "madurai", "ooty"],
    "karnataka": ["bangalore", "bengaluru", "mysore", "hampi"],
    "delhi": ["new delhi", "delhi"],
}


# ─── GENERAL HELPERS ────────────────────────────────────────

def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text.lower()) for pattern in patterns)


def _build_history_summary(
    conversation: Conversation,
    limit: int = 6,
) -> str:
    recent = conversation.messages[-limit:] if conversation.messages else []

    return (
        "\n".join(f"{message.role}: {message.content[:200]}" for message in recent)
        if recent
        else "New conversation"
    )


def _execute_tool(
    db: Session,
    user: User,
    tool_name: str,
    raw_params: dict,
):
    tool = registry.get(tool_name)

    if not tool:
        return (
            AgentMessageResponse(
                reply=f"I don't have the '{tool_name}' capability yet."
            ),
            False,
        )

    try:
        validated_params = tool.input_schema(**raw_params)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][0] if first["loc"] else "argument"

        return (
            AgentMessageResponse(
                reply=f"I need one more detail — what's the {field}?"
            ),
            True,
        )

    ctx = ToolContext(db=db, user=user)

    result = registry.dispatch(ctx, tool.name, raw_params)

    return (
        AgentMessageResponse(
            reply=result.message,
            tool_calls=[
                ToolCallInfo(
                    tool_name=tool.name,
                    args=validated_params.model_dump(mode="json"),
                    success=result.success,
                    message=result.message,
                )
            ],
            structured_data=result.data if result.data else None,
        ),
        False,
    )


def _build_confirmation_response(db: Session, user: User, tool, raw_params: dict) -> AgentMessageResponse:
    params = tool.input_schema(**raw_params)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    confirmation = create_confirmation(db, user_id=user.id, tool_name=tool.name, params=params.model_dump(mode="json"), expires_at=expires_at)
    token = jwt.encode({"user_id": user.id, "jti": confirmation.jti, "purpose": "tool_confirmation", "exp": expires_at}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    prompt = tool.confirmation_prompt(params)
    return AgentMessageResponse(reply=f"I can {prompt}. Would you like me to proceed?", needs_confirmation=True, confirmation_token=token, pending_tool=tool.name, pending_args=params.model_dump(mode="json"))

def _extract_city_from_text(text: str) -> str | None:
    """Strict city extraction. Known cities first, then regex."""

    text_lower = text.lower()

    for city in KNOWN_CITY_NAMES:
        if re.search(rf"\b{re.escape(city)}\b", text_lower):
            return city.title() if city != "new delhi" else "New Delhi"

    match = re.search(
        r"(?:in|near|around|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        text,
    )

    if match:
        return match.group(1).strip()

    return None


def _is_short_slot_reply(text: str) -> bool:
    """Replies ≤ 4 words that aren't questions are slot values, not new intents."""

    stripped = text.strip()

    if not stripped or len(stripped) > 50:
        return False

    if "?" in stripped or "!" in stripped:
        return False

    if len(stripped.split()) > 4:
        return False

    if re.match(
        r"^(?:what|why|how|when|where|who|can|could|should|would|find|show|book|plan)\b",
        stripped,
        re.IGNORECASE,
    ):
        return False

    return True


def _extract_date(text: str, marker: str) -> str | None:
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    match = re.search(
        rf"(?:{marker})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+([a-zA-Z]{{3,}})\s*(\d{{4}})?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = months.get(match.group(2).lower()[:3])

    if not month:
        return None

    year = int(match.group(3)) if match.group(3) else datetime.now().year

    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _detect_hotel_date_conflict(
    entities: dict,
) -> tuple[bool, str]:
    """Detect whether hotel date range conflicts with requested nights."""

    check_in = entities.get("check_in")
    check_out = entities.get("check_out")
    requested_nights = entities.get("nights")

    if not check_in or not check_out or requested_nights is None:
        return False, ""

    try:
        start = datetime.strptime(str(check_in), "%Y-%m-%d").date()
        end = datetime.strptime(str(check_out), "%Y-%m-%d").date()
        requested_nights = int(requested_nights)
    except (ValueError, TypeError):
        return False, ""

    actual_nights = (end - start).days

    if actual_nights <= 0:
        return True, "Check-out must be after check-in."

    if actual_nights != requested_nights:
        return (
            True,
            f"Your selected dates cover {actual_nights} nights, "
            f"but you requested {requested_nights} nights. "
            "Please confirm which duration is correct.",
        )

    return False, ""


# ─── STATE MISMATCH DETECTION ───────────────────────────────

def _detect_state_city_mismatch(
    text: str,
) -> tuple[bool, str | None]:
    low = text.lower()

    # Remove the explicitly stated departure city from destination validation.
    destination_text = re.sub(
        r"\bfrom\s+.+?\s+to\s+",
        "",
        low,
        count=1,
    )

    mentioned_state = None

    for state in STATE_KEYWORDS:
        if re.search(rf"\b{re.escape(state)}\b", destination_text):
            mentioned_state = state
            break

    if not mentioned_state:
        return False, None

    other_cities_found = []

    for other_state, cities in STATE_KEYWORDS.items():
        if other_state == mentioned_state:
            continue

        for city in cities:
            if re.search(rf"\b{re.escape(city)}\b", destination_text):
                other_cities_found.append(city)

    if other_cities_found:
        return True, (
            f"I noticed a mix-up: {', '.join(other_cities_found)} "
            f"{'are' if len(other_cities_found) > 1 else 'is'} in a different state, "
            f"not {mentioned_state.title()}. Did you mean "
            f"{', '.join(STATE_KEYWORDS[mentioned_state][:3])}, "
            f"or a {', '.join(other_cities_found)} trip?"
        )

    return False, None


# ─── MAIN HANDLER ───────────────────────────────────────────

async def handle_message(
    db: Session,
    user: User,
    text: str,
    conversation: Conversation | None = None,
    document_id: int | None = None,
) -> AgentMessageResponse:

    if not text or not text.strip():
        return AgentMessageResponse(reply="Please say something.")

    # Create a conversation for direct callers, including voice and tests.
    if conversation is None:
        conversation = Conversation(
            user_id=user.id,
            title="New Chat",
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # Never allow a conversation belonging to another user.
    if conversation.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    state = conversation.state_json or {}
    active_workflow_id = state.get("active_workflow_id")
    awaiting = state.get("awaiting")
    provider = get_provider()

    # 0. DOCUMENT
    if document_id:
        ctx = ToolContext(db=db, user=user)

        result = registry.dispatch(
            ctx,
            "answer_document",
            {
                "document_id": document_id,
                "question": text,
            },
        )

        return AgentMessageResponse(
            reply=result.message,
            structured_data=result.data if result.data else None,
        )

    # 1. AWAITING SLOT REPLY
    # Only enter if the message is a SHORT slot-like reply.
    if awaiting and _is_short_slot_reply(text):
        slot = awaiting.get("slot")

        if slot == "city":
            city = text.strip().title()

            state.pop("awaiting", None)
            state["last_location"] = city
            conversation.state_json = state
            db.commit()

            intent = awaiting.get("intent")

            if intent == "food":
                resp, _ = _execute_tool(
                    db,
                    user,
                    "discover_food",
                    {
                        "location": city,
                        "query": awaiting.get("query", "restaurant"),
                        "budget": awaiting.get("budget"),
                    },
                )
                return resp

            if intent == "hotel":
                return AgentMessageResponse(
                    reply=(
                        f"Got {city}. What are your check-in and check-out dates? "
                        "(e.g., '8 Nov to 12 Nov')"
                    )
                )

        if slot == "dates":
            check_in = _extract_date(
                text,
                "from|start|check.in|check in",
            )
            check_out = _extract_date(
                text,
                "to|end|check.out|check out",
            )

            # Also try generic "8 Nov to 12 Nov".
            if not check_in:
                match = re.search(
                    r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]{3,})"
                    r"\s*(?:to|until|-)\s*"
                    r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]{3,})",
                    text,
                    re.IGNORECASE,
                )

                if match:
                    months = {
                        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
                        "may": 5, "jun": 6, "jul": 7, "aug": 8,
                        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
                    }

                    try:
                        year = datetime.now().year

                        check_in = datetime(
                            year,
                            months[match.group(2).lower()[:3]],
                            int(match.group(1)),
                        ).strftime("%Y-%m-%d")

                        check_out = datetime(
                            year,
                            months[match.group(4).lower()[:3]],
                            int(match.group(3)),
                        ).strftime("%Y-%m-%d")

                    except (ValueError, KeyError):
                        pass

            if check_in and check_out:
                state.pop("awaiting", None)
                conversation.state_json = state
                db.commit()

                resp, _ = _execute_tool(
                    db,
                    user,
                    "search_hotels_stayapi",
                    {
                        "city": awaiting.get("city", ""),
                        "check_in": check_in,
                        "check_out": check_out,
                        "travellers": awaiting.get("travellers", 2),
                        "budget": awaiting.get("budget"),
                    },
                )

                return resp

            return AgentMessageResponse(
                reply=(
                    "I need both dates — e.g., 'from 8 Nov to 12 Nov' "
                    "or '12 Nov to 17 Nov'."
                )
            )

    # If awaiting exists but the message is NOT a short slot reply,
    # treat it as a new request — clear the awaiting state.
    if awaiting and not _is_short_slot_reply(text):
        state.pop("awaiting", None)
        conversation.state_json = state
        db.commit()

    # 2. DETERMINISTIC PRODUCTIVITY AND EXPENSE ROUTING
    parsed = parse_deterministic(text)

    if parsed:
        intent = parsed.get("intent")

        supported_intents = {
            "create_task",
            "create_reminder",
            "add_expense",
            "calculate_expense_summary",
        }

        if intent in supported_intents:
            tool = registry.get(intent)

            if not tool:
                return AgentMessageResponse(
                    reply=f"The {intent} capability is currently unavailable."
                )

            # Validate parameters before requesting confirmation or execution.
            try:
                validated_params = tool.input_schema(**parsed["params"])
            except ValidationError as exc:
                first = exc.errors()[0]
                field_name = first["loc"][0] if first["loc"] else "detail"

                return AgentMessageResponse(
                    reply=f"I need one more detail — what's the {field_name}?"
                )

            raw_params = validated_params.model_dump(mode="json")

            # Mutating expense creation requires explicit approval.
            if tool.requires_confirmation:
                return _build_confirmation_response(
                    db,
                    user,
                    tool,
                    raw_params,
                )

            response, _ = _execute_tool(
                db,
                user,
                intent,
                raw_params,
            )

            return response

    # 3. ACTIVE WORKFLOW
    if active_workflow_id:
        workflow = db.get(Workflow, active_workflow_id)

        if workflow and workflow.status in (
            "PLANNED",
            "EXECUTING",
            "AWAITING_APPROVAL",
            "PARTIALLY_COMPLETED",
        ):
            approval_reply = re.sub(r"[^a-z]+", " ", text.lower()).strip()
            explicit_approvals = {
                "yes", "yes please", "approve", "approved", "confirm",
                "confirm it", "go ahead", "proceed", "sure", "ok", "okay",
                "do it",
            }
            awaiting_step = next(
                (
                    step for step in workflow.steps_json or []
                    if step.get("status") == "AWAITING_APPROVAL"
                ),
                None,
            )

            # Never approve because a normal sentence merely contains a word
            # such as "confirm". Approval requires an explicit short reply and
            # an outstanding approval checkpoint.
            if awaiting_step and approval_reply in explicit_approvals:
                engine = WorkflowEngine(db, user)
                engine.approve_step(workflow, awaiting_step["id"])
                exec_result = engine.execute(workflow)
                return await _workflow_response(
                    db,
                    user,
                    conversation,
                    workflow,
                    exec_result,
                )

    # 4. STATE MISMATCH
    is_mismatch, mismatch_msg = _detect_state_city_mismatch(text)

    if is_mismatch:
        return AgentMessageResponse(reply=mismatch_msg)

    # 5. FINANCIAL PLANNING
    if _matches(text, FINANCIAL_PATTERNS):
        income = _extract_budget(text) or 0

        rent_m = re.search(
            r"rent\s*(?:is|of|:)?\s*[₹rs.]*\s*(\d[\d,]*)",
            text,
            re.IGNORECASE,
        )
        food_m = re.search(
            r"food\s*(?:costs?|is|:)?\s*[₹rs.]*\s*(\d[\d,]*)",
            text,
            re.IGNORECASE,
        )
        travel_m = re.search(
            r"travel\s*(?:costs?|is|:)?\s*[₹rs.]*\s*(\d[\d,]*)",
            text,
            re.IGNORECASE,
        )

        if income > 0:
            resp, _ = _execute_tool(
                db,
                user,
                "calculate_savings_plan",
                {
                    "monthly_income": income,
                    "rent": float(rent_m.group(1).replace(",", "")) if rent_m else 0,
                    "food": float(food_m.group(1).replace(",", "")) if food_m else 0,
                    "travel": float(travel_m.group(1).replace(",", "")) if travel_m else 0,
                },
            )

            return resp

        return AgentMessageResponse(
            reply="What's your monthly income and fixed expenses (rent, food, travel)?"
        )

    # 6. TRAVEL
    if _matches(text, TRAVEL_PATTERNS):
        interpreter = GoalInterpreter()

        result = await interpreter.interpret(
            text,
            _build_history_summary(conversation),
        )

        if result.get("needs_clarification"):
            return AgentMessageResponse(
                reply=result["clarification_question"]
            )

        if result.get("plan"):
            plan = result["plan"]

            match = re.search(
                r"(?:covering|including|across)\s+(.+?)(?:\s+for\b|\s+with\b|$)",
                text,
                re.IGNORECASE,
            )

            if match:
                parts = re.split(
                    r",|\s+and\s+|\s+to\s+",
                    match.group(1).strip(),
                )

                cities = [
                    part.strip()
                    for part in parts
                    if 2 < len(part.strip()) < 40
                ]

                if cities:
                    plan.context["destination"] = ", ".join(cities)

            for step in plan.steps:
                if "itinerary" in step.tool:
                    step.params["destination"] = plan.context.get(
                        "destination",
                        "",
                    )

                    if "days" in step.params:
                        try:
                            step.params["days"] = int(step.params["days"])
                        except (TypeError, ValueError):
                            step.params["days"] = 3

                for key in ("check_in", "check_out", "date"):
                    if key in step.params and isinstance(step.params[key], str):
                        step.params[key] = re.sub(
                            r"(\d{4}-\d{2}-\d{2}).*",
                            r"\1",
                            step.params[key],
                        )

                if "cab" in step.tool:
                    destination = (
                        plan.context.get("destination", "").split(",")[0].strip()
                    )

                    step.params.setdefault(
                        "pickup_location",
                        f"{destination} Airport",
                    )
                    step.params.setdefault(
                        "dropoff_location",
                        destination or "City Center",
                    )

            old = (
                db.query(Workflow)
                .filter(
                    Workflow.user_id == user.id,
                    Workflow.status.in_(
                        [
                            "PLANNED",
                            "IN_PROGRESS",
                            "AWAITING_APPROVAL",
                            "PARTIALLY_COMPLETED",
                        ]
                    ),
                )
                .order_by(Workflow.updated_at.desc())
                .first()
            )

            if old:
                old.status = "SUPERSEDED"
                db.commit()

            engine = WorkflowEngine(db, user)

            workflow = engine.create_workflow(
                conversation.id,
                plan,
            )

            state["active_workflow_id"] = workflow.id
            conversation.state_json = state
            db.commit()

            exec_result = engine.execute(workflow)

            return await _workflow_response(
                db,
                user,
                conversation,
                workflow,
                exec_result,
            )

    # 7. FOOD
    if _matches(text, FOOD_PATTERNS):
        city = _extract_city_from_text(text)
        budget = _extract_budget(text)
        food_query = "restaurant"
        low = text.lower()

        for dish in [
            "biryani", "pizza", "burger", "momos", "dosa", "idli",
            "chinese", "thali", "paneer", "chicken", "shawarma", "kebab",
        ]:
            if dish in low:
                food_query = dish
                break

        if not city:
            state["awaiting"] = {
                "slot": "city",
                "intent": "food",
                "budget": budget,
                "query": food_query,
            }

            conversation.state_json = state
            db.commit()

            return AgentMessageResponse(
                reply=(
                    "I can find that for you! Which city? "
                    "(e.g., Delhi, Mumbai, Bangalore)"
                )
            )

        state["last_location"] = city
        conversation.state_json = state
        db.commit()

        resp, _ = _execute_tool(
            db,
            user,
            "discover_food",
            {
                "location": city,
                "query": food_query,
                "budget": budget,
            },
        )

        return resp

    # 8. HOTEL
    if _matches(text, HOTEL_PATTERNS):
        city = _extract_city_from_text(text)
        check_in = _extract_date(text, "check.in|from")
        check_out = _extract_date(text, "check.out|to")
        budget = _extract_budget(text)

        if not city:
            state["awaiting"] = {
                "slot": "city",
                "intent": "hotel",
                "budget": budget,
                "travellers": _normalize_people(text) or 2,
            }

            conversation.state_json = state
            db.commit()

            return AgentMessageResponse(
                reply="Which city? (e.g., Mumbai, Delhi, Goa)"
            )

        if not check_in or not check_out:
            state["awaiting"] = {
                "slot": "dates",
                "intent": "hotel",
                "city": city,
                "budget": budget,
                "travellers": _normalize_people(text) or 2,
            }

            conversation.state_json = state
            db.commit()

            return AgentMessageResponse(
                reply=(
                    f"Got {city}. What are your check-in and check-out dates? "
                    "(e.g., '8 Nov to 12 Nov')"
                )
            )

        state["last_location"] = city
        conversation.state_json = state
        db.commit()

        resp, _ = _execute_tool(
            db,
            user,
            "search_hotels_stayapi",
            {
                "city": city,
                "check_in": check_in,
                "check_out": check_out,
                "travellers": _normalize_people(text) or 2,
                "budget": budget,
            },
        )

        return resp

    # 9. UNIVERSAL CAPABILITY-DRIVEN PLANNER
    # Legacy deterministic routes above remain intact for compatibility. Any
    # unhandled request now gets a chance to use the registered capability set
    # before falling back to a plain conversational answer.
    universal = UniversalTaskPlanner(provider=provider)
    decision = await universal.interpret(
        text,
        _build_history_summary(conversation),
    )

    if decision.get("decision") == "clarification":
        return AgentMessageResponse(reply=decision.get("reply", "What detail should I use?"))

    if decision.get("decision") == "workflow" and decision.get("plan"):
        active_workflow = (
            db.query(Workflow)
            .filter(
                Workflow.user_id == user.id,
                Workflow.status.in_(
                    ["PLANNED", "IN_PROGRESS", "AWAITING_APPROVAL", "PARTIALLY_COMPLETED"]
                ),
            )
            .order_by(Workflow.updated_at.desc())
            .first()
        )
        if active_workflow:
            active_workflow.status = "SUPERSEDED"
            db.commit()

        engine = WorkflowEngine(db, user)
        workflow = engine.create_workflow(conversation.id, decision["plan"])
        state["active_workflow_id"] = workflow.id
        conversation.state_json = state
        db.commit()
        exec_result = engine.execute(workflow)
        return await _workflow_response(
            db, user, conversation, workflow, exec_result
        )

    # The planner may explicitly provide a normal chat answer. If it is
    # unavailable or malformed, retain the existing synthesis fallback.
    planned_reply = decision.get("reply")
    if decision.get("decision") == "chat" and planned_reply:
        return AgentMessageResponse(reply=planned_reply)

    llm_reply = await provider.synthesize(
        [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
        ]
        + [{"role": "user", "content": text}],
        tool_context="No verified tools used. Answer the user's question directly.",
    )

    return AgentMessageResponse(reply=llm_reply)


# ─── WORKFLOW RESPONSE ──────────────────────────────────────

async def _workflow_response(
    db,
    user,
    conversation,
    workflow,
    exec_result,
) -> AgentMessageResponse:

    steps = workflow.steps_json or []
    status = workflow.status

    if exec_result.get("awaiting_approval"):
        step = exec_result["awaiting_approval"]

        return AgentMessageResponse(
            reply=(
                f"I'm ready to proceed with: **{step.get('approval_prompt') or step['description']}**. "
                "Please confirm before I execute this action."
            ),
            structured_data={
                "type": "workflow_status",
                "workflow_id": workflow.id,
                "steps": steps,
                "status": status,
            },
        )

    completed = [
        step for step in steps
        if step.get("status") == "COMPLETED"
    ]

    failed = [
        step for step in steps
        if step.get("status") in ("FAILED", "BLOCKED")
    ]

    trip_summary = None

    for step in steps:
        if (
            step.get("status") == "COMPLETED"
            and isinstance(step.get("result"), dict)
        ):
            if step["result"].get("type") == "trip_summary":
                trip_summary = step["result"]
                break

    if trip_summary:
        conversation.state_json = {}
        db.commit()

        msg = "Here is your trip plan."

        if status == "PARTIALLY_COMPLETED":
            msg = (
                "Here is your trip plan. Some services couldn't be loaded, "
                "but I've compiled what I could."
            )

        return AgentMessageResponse(
            reply=msg,
            structured_data=trip_summary,
        )

    if status in ("COMPLETED", "PARTIALLY_COMPLETED"):
        conversation.state_json = {}
        db.commit()

        lines = [
            f"✅ {step['description']}"
            for step in completed
        ]

        lines += [
            f"⚠️ {step['description']}: {step.get('error', 'unavailable')}"
            for step in failed
        ]

        return AgentMessageResponse(
            reply="Here's what I could put together:\n\n" + "\n".join(lines),
            structured_data={
                "type": "workflow_status",
                "workflow_id": workflow.id,
                "steps": steps,
                "status": status,
            },
        )

    if status == "FAILED":
        conversation.state_json = {}
        db.commit()

        lines = [
            f"❌ {step['description']}: {step.get('error', 'unavailable')}"
            for step in failed
        ]

        return AgentMessageResponse(
            reply="I couldn't complete the plan:\n\n" + "\n".join(lines),
            structured_data={
                "type": "workflow_status",
                "workflow_id": workflow.id,
                "steps": steps,
                "status": status,
            },
        )

    return AgentMessageResponse(
        reply="Working on it...",
        structured_data={
            "type": "workflow_status",
            "workflow_id": workflow.id,
            "steps": steps,
            "status": status,
        },
    )


# ─── CONFIRMATION HANDLER ───────────────────────────────────

async def handle_confirm(db: Session, user: User, token: str) -> AgentMessageResponse:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Confirmation token expired.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid token.")
    if str(payload.get("user_id")) != str(user.id):
        raise HTTPException(status_code=403, detail="Invalid user.")
    if payload.get("purpose") != "tool_confirmation" or not payload.get("jti"):
        raise HTTPException(status_code=400, detail="Invalid confirmation token.")
    from app.models.confirmation import Confirmation
    jti = str(payload["jti"])
    pending = db.query(Confirmation).filter(Confirmation.jti == jti, Confirmation.user_id == user.id).one_or_none()
    if pending is None:
        raise HTTPException(status_code=400, detail="Invalid confirmation.")
    tool = registry.get(pending.tool_name)
    if not tool or not tool.requires_confirmation:
        raise HTTPException(status_code=400, detail="This action does not support confirmation.")
    confirmation, error = consume_confirmation(db, jti=jti, user_id=user.id)
    if confirmation is None:
        raise HTTPException(status_code=409, detail=error or "Confirmation unavailable.")
    response, _ = _execute_tool(db, user, confirmation.tool_name, confirmation.params)
    succeeded = bool(response.tool_calls and response.tool_calls[0].success)
    finalize_confirmation(db, confirmation_id=confirmation.id, user_id=user.id, success=succeeded, message=response.reply)
    return response
