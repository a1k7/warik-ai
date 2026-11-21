"""Persistent, conversation-scoped travel mission state for Warik AI.

This module stores only explicit user constraints and workflow evidence metadata.
It never invents dates, provider prices, availability, bookings, or user preferences.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


MISSION_KEY = "travel_mission"
MISSION_VERSION = 1


class TravelConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str | None = None
    destination: str | None = None
    departure_date: str | None = None
    return_date: str | None = None
    check_in: str | None = None
    check_out: str | None = None
    trip_days: int | None = Field(default=None, ge=1, le=90)
    travellers: int | None = Field(default=None, ge=1, le=20)
    rooms: int | None = Field(default=None, ge=1, le=10)
    budget_amount: float | None = Field(default=None, gt=0)
    budget_currency: str | None = None
    cabin: str | None = None
    direct_only: bool | None = None


class TravelMission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = MISSION_VERSION
    mission_id: str = Field(default_factory=lambda: str(uuid4()))
    version: int = Field(default=1, ge=1)
    status: str = "planning"
    constraints: TravelConstraints = Field(default_factory=TravelConstraints)
    preferences: dict[str, Any] = Field(default_factory=dict)
    candidates: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    selections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    booking_evidence: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_bookings: list[dict[str, Any]] = Field(default_factory=list)
    invalidation_log: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    feasibility: dict[str, Any] = Field(default_factory=dict)
    pending_recalculations: list[dict[str, Any]] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_MONTHS = (
    "Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    "Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_DATE_RE = re.compile(
    rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})(?:\s+\d{{4}})?|"
    rf"(?:{_MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?)\b",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(
    r"(?:(₹|\bINR\b|\bRs\.?\s*)\s*)?(\d[\d,]*(?:\.\d{1,2})?)\s*(k)?",
    re.IGNORECASE,
)
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}


def _clean_place(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,-\t\n")[:80]


def _parse_date_token(token: str, reference: date) -> str | None:
    value = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", token.strip(), flags=re.I)
    value = value.replace(",", " ")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    formats = (
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
        "%d %B", "%d %b", "%B %d", "%b %d",
    )
    for fmt in formats:
        candidate = value
        if "%Y" not in fmt:
            candidate = f"{value} {reference.year}" if fmt.startswith("%d") else f"{value} {reference.year}"
            fmt = fmt + " %Y"
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_amount(text: str) -> tuple[float | None, str | None]:
    # Prefer amounts close to an explicit budget phrase or currency marker.
    patterns = (
        r"(?:budget|under|below|within|maximum|max|up to)\s*(?:of\s*)?(₹|INR|Rs\.?\s*)?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(k)?",
        r"(₹|INR|Rs\.?\s*)\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(k)?",
        r"\b(\d[\d,]*(?:\.\d{1,2})?)\s*(k)\s*(?:budget)?\b",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        groups = match.groups()
        if index == 2:
            currency, raw, suffix = None, groups[0], groups[1]
        else:
            currency, raw, suffix = groups
        try:
            amount = float(raw.replace(",", "")) * (1000 if suffix else 1)
        except (TypeError, ValueError):
            continue
        code = "INR" if currency and ("₹" in currency or "INR" in currency.upper() or "RS" in currency.upper()) else None
        return amount, code
    return None, None


def _extract_constraints(text: str, reference: date) -> dict[str, Any]:
    value = (text or "").strip()
    low = value.lower()
    found: dict[str, Any] = {}

    # Explicit route: "from Bhopal to Goa".
    route = re.search(
        r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:for|on|between|under|within|with|budget|leaving|departing)\b|[,;.!?]|$)",
        value,
        re.I,
    )
    if route:
        origin, destination = _clean_place(route.group(1)), _clean_place(route.group(2))
        # Do not interpret obvious date ranges as city routes.
        if origin and destination and not _DATE_RE.fullmatch(origin) and not _DATE_RE.fullmatch(destination):
            found["origin"] = origin
            found["destination"] = destination

    changed_destination = re.search(
        r"\b(?:change|move|switch|set)\s+(?:the\s+)?destination\s+to\s+(.+?)(?=\s+(?:and|for|under|within|with|on)\b|[,;.!?]|$)",
        value,
        re.I,
    )
    if changed_destination:
        found["destination"] = _clean_place(changed_destination.group(1))

    changed_origin = re.search(
        r"\b(?:change|move|switch|set)\s+(?:the\s+)?origin\s+to\s+(.+?)(?=\s+(?:and|for|under|within|with|on)\b|[,;.!?]|$)",
        value,
        re.I,
    )
    if changed_origin:
        found["origin"] = _clean_place(changed_origin.group(1))

    # Destination-only phrases are useful for a new trip or a follow-up.
    if "destination" not in found:
        destination_match = re.search(
            r"\b(?:trip|travel|fly|go|going|stay|hotel|visit|vacation|holiday)\s+(?:to|in)\s+(.+?)(?=\s+(?:from|for|on|between|under|within|with|budget|for\s+\d)\b|[,;.!?]|$)",
            value,
            re.I,
        )
        if destination_match:
            candidate = _clean_place(destination_match.group(1))
            if candidate and not _DATE_RE.fullmatch(candidate):
                found["destination"] = candidate

    duration = re.search(r"\b(\d{1,2})\s*[- ]?days?\b", low)
    if duration:
        days = int(duration.group(1))
        if 1 <= days <= 90:
            found["trip_days"] = days

    people = re.search(
        r"\b(?:for\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:people|persons|travellers|travelers|adults|guests|pax)\b",
        low,
    )
    if people:
        token = people.group(1)
        count = int(token) if token.isdigit() else _WORD_NUMBERS[token]
        if 1 <= count <= 20:
            found["travellers"] = count
    elif re.search(r"\bsolo\s+(?:trip|travel|traveller|traveler)\b", low):
        found["travellers"] = 1
    elif re.search(r"\b(?:couple|two of us)\b", low):
        found["travellers"] = 2

    rooms = re.search(r"\b(\d{1,2})\s+rooms?\b", low)
    if rooms and 1 <= int(rooms.group(1)) <= 10:
        found["rooms"] = int(rooms.group(1))

    amount, currency = _extract_amount(value)
    if amount is not None and amount > 0:
        found["budget_amount"] = amount
        if currency:
            found["budget_currency"] = currency

    if re.search(r"\b(?:nonstop|non-stop|direct flight|direct flights)\b", low):
        found["direct_only"] = True
    elif re.search(r"\b(?:any stops|stops are fine|connecting flights? (?:are )?okay)\b", low):
        found["direct_only"] = False

    cabin = re.search(r"\b(economy|premium economy|business class|first class)\b", low)
    if cabin:
        found["cabin"] = cabin.group(1).title()

    date_tokens = [m.group(0) for m in _DATE_RE.finditer(value)]
    parsed_dates = [d for token in date_tokens if (d := _parse_date_token(token, reference))]
    if parsed_dates:
        if len(parsed_dates) >= 2:
            found["departure_date"], found["return_date"] = parsed_dates[0], parsed_dates[1]
        else:
            one = parsed_dates[0]
            if re.search(r"\b(?:return|back|coming back)\b", low):
                found["return_date"] = one
            elif re.search(r"\b(?:check[- ]?in)\b", low):
                found["check_in"] = one
            elif re.search(r"\b(?:check[- ]?out)\b", low):
                found["check_out"] = one
            else:
                found["departure_date"] = one

    # Explicit check-in/check-out language wins over generic trip date parsing.
    if "check_in" in found and "departure_date" in found and len(parsed_dates) == 1:
        found.pop("departure_date", None)
    if "check_out" in found and "return_date" in found and len(parsed_dates) == 1:
        found.pop("return_date", None)

    return found


_FIELD_ARTIFACT_DEPENDENCIES = {
    "origin": {"flights", "transfers", "routes", "itinerary", "budget"},
    "destination": {"flights", "hotels", "transfers", "routes", "itinerary", "budget"},
    "departure_date": {"flights", "hotels", "transfers", "routes", "itinerary", "budget"},
    "return_date": {"flights", "hotels", "transfers", "routes", "itinerary", "budget"},
    "check_in": {"hotels", "itinerary", "budget"},
    "check_out": {"hotels", "itinerary", "budget"},
    "trip_days": {"hotels", "itinerary", "budget"},
    "travellers": {"flights", "hotels", "transfers", "routes", "budget"},
    "rooms": {"hotels", "budget"},
    "budget_amount": {"budget"},
    "budget_currency": {"budget"},
    "cabin": {"flights"},
    "direct_only": {"flights"},
}


def _invalidate_dependents(mission: TravelMission, changed_fields: set[str], timestamp: str) -> None:
    """Stale dependent recommendations and enqueue their evidence-backed reruns."""
    affected: set[str] = set()
    for field in changed_fields:
        affected.update(_FIELD_ARTIFACT_DEPENDENCIES.get(field, set()))

    fallback_tools = {
        "flights": "search_flights_real",
        "hotels": "search_hotels_stayapi",
        "transfers": "get_cab_links",
        "routes": "optimize_route",
        "itinerary": "generate_advanced_itinerary",
        "budget": "__local_feasibility__",
    }
    pending = [
        item for item in mission.pending_recalculations
        if isinstance(item, dict) and item.get("artifact") not in affected
    ]
    changed: list[str] = []

    for artifact in sorted(affected):
        item = mission.artifacts.get(artifact)
        if not isinstance(item, dict) or item.get("status") != "current":
            continue
        booking_status = str(
            item.get("booking_status") or item.get("reservation_status") or ""
        ).lower()
        if booking_status in {"confirmed", "booked", "ticketed", "verified"}:
            continue
        if str(item.get("status") or "").lower() in {
            "confirmed", "booked", "ticketed", "verified_booking"
        }:
            continue

        item["status"] = "stale"
        item["stale_at"] = timestamp
        reason = "Changed mission constraints: " + ", ".join(sorted(changed_fields))
        item["stale_reason"] = reason
        changed.append(artifact)

        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        pending.append({
            "queue_id": str(uuid4()),
            "artifact": artifact,
            "tool_name": evidence.get("tool_name") or fallback_tools.get(artifact),
            "params": deepcopy(evidence.get("query_params") or {}),
            "status": "pending",
            "reason": reason,
            "queued_at": timestamp,
            "requires_fresh_provider_result": artifact in {"flights", "hotels", "transfers"},
        })

    mission.pending_recalculations = pending[-30:]
    if changed:
        mission.invalidation_log.append({
            "at": timestamp,
            "changed_fields": sorted(changed_fields),
            "affected_artifacts": changed,
        })
        mission.invalidation_log = mission.invalidation_log[-30:]



def update_travel_mission(conversation: Any, user_text: str, reference_date: date | None = None) -> dict[str, Any] | None:
    """Merge explicit travel constraints into Conversation.state_json.

    New missions start only on a travel-related request. Existing missions accept
    explicit travel updates and common short travel follow-ups without clearing slots.
    """
    text = (user_text or "").strip()
    if not text:
        return None
    state = dict(getattr(conversation, "state_json", None) or {})
    existing = state.get(MISSION_KEY)
    low = text.lower()
    travel_signal = bool(re.search(
        r"\b(trips?|travel|flights?|fly|airfares?|hotels?|stays?|accommodations?|vacations?|holidays?|itineraries?|airports?|cabs?|taxis?|transfers?|getaways?)\b",
        low,
    ))
    followup_signal = bool(re.search(
        r"\b(make it cheaper|cheaper|change (?:the )?(?:date|dates|flight|hotel|destination|origin)|move (?:the )?(?:date|flight|hotel)|increase (?:the )?budget|reduce (?:the )?budget|add (?:a )?(?:traveller|traveler|room)|remove (?:a )?(?:traveller|traveler|room)|nonstop|non-stop|business class|economy|(?:choose|select|pick|use|switch\s+to|change\s+to)\s+(?:the\s+)?(?:flight\s+)?(?:option\s*)?#?\d+)\b",
        low,
    ))
    followup_signal = followup_signal or bool(re.search(
        r"\b(?:choose|select|pick)\s+(?:the\s+)?(?:flight\s*)?\d+\b",
        low,
    ))
    followup_signal = followup_signal or bool(re.search(
        r"\b(?:choose|select|pick)\s+(?:the\s+)?hotel\s+\d+\b",
        low,
    ))
    if not existing and not travel_signal:
        return None
    if existing and not travel_signal and not followup_signal:
        return existing

    reference = reference_date or date.today()
    parsed = _extract_constraints(text, reference)
    try:
        mission = TravelMission.model_validate(existing) if isinstance(existing, dict) else TravelMission()
    except Exception:
        # Invalid older mission state is quarantined rather than propagated.
        mission = TravelMission()

    old_constraints = mission.constraints.model_dump()
    merged = {**old_constraints, **parsed}
    # Avoid treating the same explicitly repeated value as a mutation.
    changed_fields = {key for key, value in parsed.items() if old_constraints.get(key) != value}
    mission.constraints = TravelConstraints.model_validate(merged)
    timestamp = _now()
    if changed_fields:
        mission.version += 1
        _invalidate_dependents(mission, changed_fields, timestamp)
    mission.updated_at = timestamp

    selection_match = re.search(
        r"\b(?:choose|select|pick|use|switch\s+to|change\s+to)\s+(?:the\s+)?(?:flight\s+)?(?:option\s*)?#?(\d+)\b",
        low,
    )
    if selection_match:
        _select_flight_candidate(mission, int(selection_match.group(1)), timestamp)
    hotel_selection_match = re.search(
        r"\b(?:choose|select|pick)\s+(?:the\s+)?hotel\s+(?:option\s*)?#?(\d+)\b",
        low,
    )
    if hotel_selection_match:
        _select_hotel_candidate(mission, int(hotel_selection_match.group(1)), timestamp)


    from app.services.context.travel_feasibility import evaluate_travel_feasibility
    mission.feasibility = evaluate_travel_feasibility(mission.model_dump(mode="json"))
    state[MISSION_KEY] = mission.model_dump(mode="json")
    conversation.state_json = state
    return state[MISSION_KEY]


def mark_travel_artifact_current(
    mission_data: dict[str, Any],
    artifact: str,
    *,
    provider: str,
    source_type: str,
    retrieved_at: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record provenance for an artifact without asserting that it is booked."""
    if artifact not in {"flights", "hotels", "transfers", "routes", "itinerary", "budget"}:
        raise ValueError("Unsupported travel artifact")
    mission = TravelMission.model_validate(mission_data)
    data = mission.model_dump(mode="json")
    timestamp = retrieved_at or _now()
    data["artifacts"][artifact] = {
        "status": "current",
        "provider": provider,
        "source_type": source_type,
        "retrieved_at": timestamp,
        "mission_version": mission.version,
        "evidence": deepcopy(evidence or {}),
    }
    fingerprint_payload = mission.constraints.model_dump()
    data["artifacts"][artifact]["constraints_fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return data


def format_travel_mission_context(mission_data: dict[str, Any] | None, max_chars: int = 1100) -> str:
    """Render compact, explicit mission state for planner context."""
    if not isinstance(mission_data, dict):
        return ""
    try:
        mission = TravelMission.model_validate(mission_data)
    except Exception:
        return ""
    constraints = {
        key: value for key, value in mission.constraints.model_dump().items()
        if value is not None
    }
    artifacts = {
        key: {
            "status": value.get("status"),
            "provider": value.get("provider"),
            "retrieved_at": value.get("retrieved_at"),
        }
        for key, value in mission.artifacts.items() if isinstance(value, dict)
    }
    payload = {
        "mission_id": mission.mission_id,
        "version": mission.version,
        "status": mission.status,
        "explicit_constraints": constraints,
        "preferences": mission.preferences,
        "selected_options": mission.selections,
        "artifact_freshness": artifacts,
        "feasibility": mission.feasibility,
        "pending_recalculations": mission.pending_recalculations,
        "instruction": "Preserve unchanged constraints. Do not treat stale results, estimates, handoff links, or recommendations as bookings.",
    }
    rendered = "ACTIVE TRAVEL MISSION (structured task state, not a source of provider availability):\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return "SAFETY: Do not treat stale results, estimates, handoff links, or recommendations as bookings.\n" + (rendered[:max_chars])

def _flight_operational_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    """Return the operational itinerary signature, using actual normalized segments."""
    segments = candidate.get("segments") or []
    normalized = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        normalized.append((
            str(segment.get("origin") or "").upper(),
            str(segment.get("destination") or "").upper(),
            str(segment.get("departure") or ""),
            str(segment.get("arrival") or ""),
        ))
    if normalized:
        return tuple(normalized)
    return (
        str(candidate.get("origin") or "").upper(),
        str(candidate.get("destination") or "").upper(),
        str(candidate.get("departure") or ""),
        str(candidate.get("arrival") or ""),
        str(candidate.get("date") or ""),
    )



def _invalidate_selected_flight_dependents(
    mission: TravelMission,
    affected: set[str],
    timestamp: str,
    reason: str,
    changed_field: str = "selected_flight",
) -> None:
    changed = []
    fallback_tools = {
        "hotels": "search_hotels_stayapi",
        "transfers": "get_cab_links",
        "routes": "optimize_route",
        "itinerary": "generate_advanced_itinerary",
        "budget": "calculate_trip_budget",
    }
    existing_pending = [
        item for item in mission.pending_recalculations
        if isinstance(item, dict) and item.get("artifact") not in affected
    ]
    for artifact in sorted(affected):
        item = mission.artifacts.get(artifact)
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        booking_status = str(
            item.get("booking_status") or item.get("reservation_status") or ""
        ).lower()
        if status in {"confirmed", "booked", "ticketed", "verified_booking"}:
            continue
        if booking_status in {"confirmed", "booked", "ticketed", "verified"}:
            continue
        if status != "current":
            continue
        item["status"] = "stale"
        item["stale_at"] = timestamp
        item["stale_reason"] = reason
        changed.append(artifact)
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        existing_pending.append({
            "artifact": artifact,
            "tool_name": evidence.get("tool_name") or fallback_tools.get(artifact),
            "params": deepcopy(evidence.get("query_params") or {}),
            "status": "pending",
            "reason": reason,
            "queued_at": timestamp,
            "requires_fresh_provider_result": artifact in {"flights", "hotels", "transfers"},
        })
    mission.pending_recalculations = existing_pending[-30:]
    if changed:
        mission.invalidation_log.append({
            "at": timestamp,
            "changed_fields": [changed_field],
            "affected_artifacts": changed,
            "reason": reason,
        })
        mission.invalidation_log = mission.invalidation_log[-30:]



def _select_flight_candidate(
    mission: TravelMission,
    one_based_index: int,
    timestamp: str,
) -> bool:
    candidates = mission.candidates.get("flights") or []
    index = one_based_index - 1
    if index < 0 or index >= len(candidates):
        return False
    candidate = candidates[index]
    if not isinstance(candidate, dict):
        return False
    previous_record = mission.selections.get("flights")
    previous = previous_record.get("candidate") if isinstance(previous_record, dict) else None
    if previous == candidate:
        return False

    if isinstance(previous, dict):
        previous_schedule = _flight_operational_signature(previous)
        next_schedule = _flight_operational_signature(candidate)
        if previous_schedule != next_schedule:
            affected = {"hotels", "transfers", "routes", "itinerary", "budget"}
            reason = (
                "Selected flight airports, dates, or departure/arrival times changed; "
                "dependent hotel, transfer, route, itinerary, and budget results need review."
            )
        else:
            previous_price = (previous.get("price_amount", previous.get("price")), previous.get("currency"))
            next_price = (candidate.get("price_amount", candidate.get("price")), candidate.get("currency"))
            affected = {"budget"} if previous_price != next_price else set()
            reason = "Selected flight price or currency changed; recalculate the budget."
    else:
        # First selection establishes the baseline; without a previous flight
        # there is no schedule delta to invalidate. Later schedule changes do.
        affected = set()
        reason = "Initial flight selection established; no prior flight schedule to compare."

    if affected:
        _invalidate_selected_flight_dependents(mission, affected, timestamp, reason)
    mission.version += 1
    mission.selections["flights"] = {
        "candidate_index": one_based_index,
        "candidate": deepcopy(candidate),
        "selected_at": timestamp,
        "selection_status": "selected_not_booked",
    }
    flight_artifact = mission.artifacts.get("flights")
    if isinstance(flight_artifact, dict) and flight_artifact.get("status") == "current":
        flight_artifact["mission_version"] = mission.version
    mission.updated_at = timestamp
    return True






def _select_hotel_candidate(
    mission: TravelMission,
    one_based_index: int,
    timestamp: str,
) -> bool:
    candidates = mission.candidates.get("hotels") or []
    index = one_based_index - 1
    if index < 0 or index >= len(candidates):
        return False
    candidate = candidates[index]
    if not isinstance(candidate, dict):
        return False
    previous_record = mission.selections.get("hotels")
    previous = previous_record.get("candidate") if isinstance(previous_record, dict) else None
    if previous == candidate:
        return False
    reason = "Selected hotel changed; transfer, route, itinerary, and budget assumptions need recalculation."
    _invalidate_selected_flight_dependents(
        mission,
        {"transfers", "routes", "itinerary", "budget"},
        timestamp,
        reason,
        changed_field="selected_hotel",
    )
    mission.version += 1
    mission.selections["hotels"] = {
        "candidate_index": one_based_index,
        "candidate": deepcopy(candidate),
        "selected_at": timestamp,
        "selection_status": "selected_not_booked",
    }
    hotel_artifact = mission.artifacts.get("hotels")
    if isinstance(hotel_artifact, dict) and hotel_artifact.get("status") == "current":
        hotel_artifact["mission_version"] = mission.version
    mission.updated_at = timestamp
    return True
