"""Evidence attachment for completed travel workflow tools.

Only normalized tool outputs are stored. This module never turns a search result,
route estimate or handoff link into a booking confirmation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from typing import Any

from app.models import Conversation
from app.services.context.travel_mission import (
    MISSION_KEY,
    TravelMission,
    mark_travel_artifact_current,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_for_tool(tool_name: str) -> str | None:
    name = (tool_name or "").lower()
    if "flight" in name:
        return "flights"
    if "hotel" in name or "stay" in name:
        return "hotels"
    if "cab" in name or "transport" in name:
        return "transfers"
    if "route" in name:
        return "routes"
    if "itinerary" in name or "trip_summary" in name:
        return "itinerary"
    if "budget" in name:
        return "budget"
    return None


def _source_type(artifact: str, data: dict[str, Any]) -> str:
    if data.get("type") == "transport_links":
        return "external_handoff"
    if artifact == "routes":
        return "straight_line_estimate"
    if data.get("live_inventory") is True:
        return "live_provider_search"
    if data.get("live_inventory") is False:
        return "provider_unavailable_or_handoff"
    if artifact == "itinerary":
        return "generated_itinerary"
    if artifact == "budget":
        return "calculated_estimate"
    return "tool_result_unverified"


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def attach_tool_result_to_mission(
    conversation: Any,
    *,
    tool_name: str,
    params: dict[str, Any] | None,
    result_data: dict[str, Any],
    selected_provider_id: str | None = None,
) -> bool:
    """Attach normalized results without manufacturing provider provenance.

    Returns True only when the artifact is current evidence. Handoffs,
    unavailable providers and results without explicit provider/timestamp data
    are retained for diagnosis but cannot complete a refresh queue item.
    """
    artifact = _artifact_for_tool(tool_name)
    if artifact is None or not isinstance(result_data, dict):
        return False

    state = dict(getattr(conversation, "state_json", None) or {})
    raw_mission = state.get(MISSION_KEY)
    if not isinstance(raw_mission, dict):
        return False
    mission = TravelMission.model_validate(raw_mission)
    data = _json_copy(result_data)

    # An empty route result is not route evidence.
    if artifact == "routes" and (data.get("type") != "route_estimate" or not data.get("legs")):
        return False

    if artifact == "routes" and isinstance(data.get("legs"), list):
        candidates = [item for item in data.get("legs", []) if isinstance(item, dict)][:30]
    else:
        raw_candidates = data.get("items")
        if isinstance(raw_candidates, list):
            candidates = [item for item in raw_candidates if isinstance(item, dict)][:10]
        elif artifact == "transfers" and isinstance(data.get("links"), dict):
            candidates = [{
                "kind": "external_handoff",
                "origin": data.get("origin"),
                "destination": data.get("destination"),
                "links": data.get("links"),
                "disclaimer": data.get("disclaimer"),
            }]
        else:
            candidates = []

    mission.candidates[artifact] = candidates
    metadata = data.get("provider_metadata") if isinstance(data.get("provider_metadata"), dict) else {}
    provider_value = data.get("provider") or selected_provider_id
    provider = str(provider_value).strip()[:100] if isinstance(provider_value, str) and provider_value.strip() else None
    retrieved_value = data.get("retrieved_at") or data.get("searched_at") or metadata.get("created_at")
    provider_retrieved_at = str(retrieved_value).strip()[:120] if isinstance(retrieved_value, str) and retrieved_value.strip() else None
    captured_at = _now()
    source_type = _source_type(artifact, data)
    live_inventory = data.get("live_inventory")
    attribution_verified = bool(provider)
    timestamp_verified = bool(provider_retrieved_at)

    currencies = sorted({
        str(item.get("currency")).upper()
        for item in candidates
        if item.get("currency")
    })
    evidence = {
        "tool_name": tool_name,
        "query_params": _json_copy(params or {}),
        "candidate_count": len(candidates),
        "resolution_status": data.get("resolution_status"),
        "live_inventory": live_inventory,
        "price_basis": data.get("price_basis"),
        "currencies": currencies,
        "provider_metadata": metadata,
        "search_url": data.get("search_url"),
        "road_distance_km": data.get("road_distance_km"),
        "travel_duration_minutes": data.get("travel_duration_minutes"),
        "live_route_verified": data.get("live_route_verified"),
        "provider_attribution_verified": attribution_verified,
        "provider_retrieval_timestamp_verified": timestamp_verified,
        "provider_result_verified": live_inventory is True,
        "captured_at": captured_at,
    }
    if artifact == "hotels":
        evidence["cancellation_fields"] = [
            key for key in ("is_free_cancellable", "is_no_prepayment")
            if any(key in item for item in candidates)
        ]
        evidence["total_stay_quotes"] = sum(
            1 for item in candidates if item.get("total_stay_amount") is not None
        )
    if artifact == "flights":
        evidence["segment_counts"] = [len(item.get("segments") or []) for item in candidates]

    updated = mark_travel_artifact_current(
        mission.model_dump(mode="json"),
        artifact,
        provider=provider or "unknown",
        source_type=source_type,
        retrieved_at=provider_retrieved_at or captured_at,
        evidence=evidence,
    )
    mission = TravelMission.model_validate(updated)
    artifact_record = mission.artifacts[artifact]
    artifact_record["provider"] = provider
    artifact_record["retrieved_at"] = provider_retrieved_at
    artifact_record["captured_at"] = captured_at
    artifact_record["evidence"] = evidence

    # Provider-backed search evidence is current only when all three facts
    # exist: live inventory was queried, the actual provider is identified,
    # and the provider supplied a retrieval/search timestamp.
    if artifact in {"flights", "hotels"}:
        if live_inventory is True and attribution_verified and timestamp_verified:
            artifact_record["status"] = "current"
        elif live_inventory is False and data.get("search_url"):
            artifact_record["status"] = "handoff"
        elif live_inventory is False:
            artifact_record["status"] = "unavailable"
        else:
            artifact_record["status"] = "unverified"
    elif artifact == "transfers":
        if data.get("type") == "transport_links":
            artifact_record["status"] = "handoff"
            artifact_record["retrieved_at"] = None
        elif live_inventory is True and attribution_verified and timestamp_verified:
            artifact_record["status"] = "current"
        else:
            artifact_record["status"] = "unverified"
    else:
        # Local calculations, generated itineraries and straight-line route
        # estimates may be current as generated artifacts, but are not provider
        # retrievals. Their capture time is recorded separately.
        artifact_record["status"] = "current"
        artifact_record["retrieved_at"] = None

    freshness_status = artifact_record["status"]
    mission.evidence.append({
        "artifact": artifact,
        "provider": provider,
        "source_type": source_type,
        "retrieved_at": provider_retrieved_at,
        "captured_at": captured_at,
        "mission_version": artifact_record["mission_version"],
        "constraints_fingerprint": artifact_record["constraints_fingerprint"],
        "candidate_count": len(candidates),
        "freshness_status": freshness_status,
        "provider_attribution_verified": attribution_verified,
        "provider_retrieval_timestamp_verified": timestamp_verified,
    })
    mission.evidence = mission.evidence[-100:]

    if freshness_status == "current":
        mission.pending_recalculations = [
            item for item in mission.pending_recalculations
            if not isinstance(item, dict) or item.get("artifact") != artifact
        ]

    from app.services.context.travel_feasibility import evaluate_travel_feasibility
    mission.feasibility = evaluate_travel_feasibility(mission.model_dump(mode="json"))
    mission.updated_at = _now()
    state[MISSION_KEY] = mission.model_dump(mode="json")
    conversation.state_json = state
    return freshness_status == "current"



def capture_workflow_tool_result(
    *,
    db: Any,
    workflow: Any,
    tool_name: str,
    params: dict[str, Any] | None,
    result_data: dict[str, Any],
    selected_provider_id: str | None = None,
) -> bool:
    """Resolve workflow -> owned goal -> conversation and attach a fresh result.

    Recalculation workflows carry an expected mission version. Results from an
    older mission snapshot are discarded and the queue item is returned to pending.
    """
    from app.models.workflow import Goal

    goal_id = getattr(workflow, "goal_id", None)
    if goal_id is None:
        return False
    goal = db.query(Goal).filter(
        Goal.id == goal_id,
        Goal.user_id == getattr(workflow, "user_id", None),
    ).first()
    if goal is None or goal.conversation_id is None:
        return False
    conversation = db.query(Conversation).filter(
        Conversation.id == goal.conversation_id,
        Conversation.user_id == goal.user_id,
    ).first()
    if conversation is None:
        return False

    context = dict(getattr(goal, "context_json", None) or {})
    recalculation = context.get("travel_recalculation")
    if isinstance(recalculation, dict):
        state = dict(getattr(conversation, "state_json", None) or {})
        raw_mission = state.get(MISSION_KEY)
        if not isinstance(raw_mission, dict):
            return False
        expected_id = recalculation.get("mission_id")
        expected_version = recalculation.get("mission_version")
        if (
            raw_mission.get("mission_id") != expected_id
            or raw_mission.get("version") != expected_version
        ):
            queue_ids = set(recalculation.get("queue_ids") or [])
            changed = False
            for item in raw_mission.get("pending_recalculations") or []:
                if isinstance(item, dict) and item.get("queue_id") in queue_ids:
                    item["status"] = "pending"
                    item["workflow_id"] = None
                    item["reason"] = "Mission changed while this search was running; a fresh result is required."
                    changed = True
            if changed:
                state[MISSION_KEY] = raw_mission
                conversation.state_json = state
                db.commit()
            return False

    return attach_tool_result_to_mission(
        conversation,
        tool_name=tool_name,
        params=params,
        result_data=result_data,
        selected_provider_id=selected_provider_id,
    )



# Gmail metadata is only a discovery signal. It is never a confirmed booking
# until the user explicitly reviews and confirms the matching message.
_GMAIL_NEGATIVE_CONTEXT = (
    "application", "partnership", "newsletter", "internship", "career",
    "job opportunity", "marketing", "promotion", "advertisement",
)
_GMAIL_CONFIRMATION_PATTERNS = (
    r"\b(?:booking|reservation|flight|hotel|ticket)\s+(?:is\s+)?confirmed\b",
    r"\bconfirmed\s+(?:booking|reservation|flight|hotel|ticket)\b",
    r"\b(?:e[ -]?ticket|boarding pass|pnr)\b",
    r"\b(?:booking|reservation)\s+(?:id|reference|confirmation)\b",
    r"\bconfirmation\s+(?:code|number)\b",
    r"\byour\s+(?:flight|hotel|trip)\s+(?:is\s+)?confirmed\b",
)


def _gmail_confirmation_signals(item: dict[str, Any]) -> list[str]:
    subject = str(item.get("subject") or "")
    sender = str(item.get("from") or "")
    snippet = str(item.get("snippet") or "")
    text = f"{subject} {sender} {snippet}".casefold()
    if any(term in text for term in _GMAIL_NEGATIVE_CONTEXT):
        return []
    # Respect the existing classifier, but never rely on category alone.
    if str(item.get("category") or "").casefold() != "travel":
        return []
    return [pattern for pattern in _GMAIL_CONFIRMATION_PATTERNS if re.search(pattern, text, re.I)]


def attach_gmail_booking_evidence(
    conversation: Any,
    *,
    items: list[dict[str, Any]],
    retrieved_at: str | None = None,
) -> int:
    """Attach strong Gmail confirmation candidates as pending review records."""
    state = dict(getattr(conversation, "state_json", None) or {})
    raw_mission = state.get(MISSION_KEY)
    if not isinstance(raw_mission, dict):
        return 0
    mission = TravelMission.model_validate(raw_mission)
    existing_ids = {
        str(item.get("message_id"))
        for item in mission.booking_evidence + mission.confirmed_bookings
        if isinstance(item, dict) and item.get("message_id")
    }
    imported = 0
    retrieved = retrieved_at or _now()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("message_id") or "").strip()
        if not message_id or message_id in existing_ids:
            continue
        signals = _gmail_confirmation_signals(item)
        if not signals:
            continue
        record = {
            "message_id": message_id,
            "source": "Gmail",
            "source_type": "email_metadata_confirmation_candidate",
            "status": "needs_user_review",
            "confirmation_state": "unverified",
            "subject": str(item.get("subject") or "")[:300],
            "from": str(item.get("from") or "")[:300],
            "received_at": str(item.get("received_at") or "")[:120],
            "snippet": str(item.get("snippet") or "")[:280],
            "matched_signals": signals,
            "retrieved_at": retrieved,
            "mission_version": mission.version,
        }
        mission.booking_evidence.append(record)
        existing_ids.add(message_id)
        imported += 1
    if imported:
        mission.booking_evidence = mission.booking_evidence[-100:]
        mission.evidence.append({
            "artifact": "booking_evidence",
            "provider": "Gmail",
            "source_type": "email_metadata_confirmation_candidate",
            "retrieved_at": retrieved,
            "mission_version": mission.version,
            "candidate_count": imported,
            "status": "needs_user_review",
        })
        mission.evidence = mission.evidence[-100:]
        mission.updated_at = _now()
        state[MISSION_KEY] = mission.model_dump(mode="json")
        conversation.state_json = state
    return imported


def confirm_gmail_booking_in_mission(
    conversation: Any,
    *,
    message_id: str,
) -> dict[str, Any] | None:
    """Promote one pending Gmail candidate only after an explicit user action."""
    state = dict(getattr(conversation, "state_json", None) or {})
    raw_mission = state.get(MISSION_KEY)
    if not isinstance(raw_mission, dict):
        return None
    mission = TravelMission.model_validate(raw_mission)
    if any(
        isinstance(item, dict) and str(item.get("message_id")) == str(message_id)
        for item in mission.confirmed_bookings
    ):
        return next(
            item for item in mission.confirmed_bookings
            if isinstance(item, dict) and str(item.get("message_id")) == str(message_id)
        )
    pending = next(
        (item for item in mission.booking_evidence
         if isinstance(item, dict)
         and str(item.get("message_id")) == str(message_id)
         and item.get("status") == "needs_user_review"),
        None,
    )
    if pending is None:
        return None
    confirmed = deepcopy(pending)
    confirmed.update({
        "status": "confirmed_by_user",
        "confirmation_state": "user_confirmed_from_email",
        "confirmed_at": _now(),
        "confirmation_method": "explicit_user_action",
    })
    pending["status"] = "user_confirmed"
    pending["confirmed_at"] = confirmed["confirmed_at"]
    mission.confirmed_bookings.append(confirmed)
    mission.confirmed_bookings = mission.confirmed_bookings[-100:]
    mission.evidence.append({
        "artifact": "confirmed_booking",
        "provider": "Gmail",
        "source_type": "explicit_user_confirmation_of_email_evidence",
        "message_id": str(message_id),
        "retrieved_at": confirmed["retrieved_at"],
        "confirmed_at": confirmed["confirmed_at"],
        "mission_version": mission.version,
        "status": "confirmed_by_user",
    })
    mission.evidence = mission.evidence[-100:]
    mission.updated_at = _now()
    state[MISSION_KEY] = mission.model_dump(mode="json")
    conversation.state_json = state
    return confirmed
