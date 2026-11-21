"""Deterministic, evidence-bounded responses for persisted travel missions.

This module deliberately does not consult conversation history or an LLM. It
answers travel status/audit questions only from Conversation.state_json.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.schemas.agent import AgentMessageResponse
from app.services.context.travel_mission import MISSION_KEY, TravelMission


def _intent_for(text: str) -> str | None:
    value = (text or "").strip().casefold()
    if not value:
        return None
    # Gmail discovery is an actual connector action, not a local ledger read.
    if re.search(r"\b(?:check|search|look in|find)\b.{0,45}\b(?:gmail|email|inbox|mailbox)\b", value):
        return None
    if re.search(r"\b(?:audit|full audit|complete audit)\b", value):
        return "audit"
    if (
        re.search(r"\bselected options?\b", value)
        and re.search(r"\b(?:recommendations?|handoffs?|booked|booking|confirmed)\b", value)
    ) or re.search(r"\bwhich options? (?:are|is) selected\b", value):
        return "options"
    if re.search(r"\b(?:queue|pending|blocked|deferred|recalculation tasks?)\b", value):
        return "queue"
    if re.search(r"\b(?:where did|where do|where .*\b(?:come|came) from|results? .*\b(?:come|came) from|provider attribution|actual provider|provenance|retrieved at|retrieval time|live inventory|source of (?:the )?(?:flight|hotel)|independent(?:ly)? verif)\b", value):
        return "provenance"
    if (
        re.search(r"\b(?:have you|did you|has warik|what(?:'s| is) (?:the )?status|show me (?:which|whether)|which options are|what is)\b.{0,100}\b(?:booked|booking|reserved|reservation|confirmed|confirmation|flight|hotel|transfer)\b", value)
        or re.search(r"\b(?:booking status|confirmed bookings|what(?:'s| is) booked|anything booked|any bookings)\b", value)
        or re.search(r"\b(?:are|is)\b.{0,60}\b(?:my |the )?(?:flight|hotel|transfer|trip|reservation|booking)\b.{0,30}\b(?:booked|reserved|confirmed)\b", value)
        or re.search(r"\b(?:which|what)\b.{0,80}\b(?:bookings?|reservations?)\b.{0,40}\b(?:confirmation|evidence|status)\b", value)
    ):
        return "bookings"
    if re.search(r"\b(?:feasib|within (?:my|the) budget|budget fit|fit (?:my|the) budget)\b", value):
        return "feasibility"
    if re.search(r"\b(?:cost breakdown|trip cost|total cost|costs? of (?:my|the) trip|expense breakdown|how much (?:will|does) (?:my|the) trip)\b", value):
        return "cost"
    if re.search(r"\b(?:summari[sz]e|what do you know|current trip details|trip constraints|travel constraints)\b", value):
        return "summary"
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_verified_live_artifact(record: dict[str, Any]) -> bool:
    evidence = _dict(record.get("evidence"))
    return bool(
        record.get("status") == "current"
        and evidence.get("live_inventory") is True
        and evidence.get("provider_attribution_verified") is True
        and evidence.get("provider_retrieval_timestamp_verified") is True
    )


def _artifact_status(name: str, record: dict[str, Any]) -> str:
    status = str(record.get("status") or "unknown").lower()
    source_type = str(record.get("source_type") or "").lower()
    if status == "current" and name in {"flights", "hotels"} and not _is_verified_live_artifact(record):
        return "unverified_legacy"
    if status == "current" and name == "transfers" and source_type == "external_handoff":
        return "handoff_only"
    return status


def _constraints(mission: dict[str, Any]) -> dict[str, Any]:
    values = _dict(mission.get("constraints"))
    return {key: value for key, value in values.items() if value is not None}


def _selected(mission: dict[str, Any], artifact: str) -> dict[str, Any] | None:
    selection = _dict(_dict(mission.get("selections")).get(artifact))
    candidate = selection.get("candidate")
    return selection if isinstance(candidate, dict) else None


def _money(candidate: dict[str, Any], keys: tuple[str, ...]) -> tuple[float, str] | None:
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            amount = float(value)
        elif isinstance(value, str) and re.fullmatch(r"\d[\d,]*(?:\.\d{1,2})?", value.strip()):
            amount = float(value.replace(",", ""))
        else:
            continue
        currency = candidate.get("currency") or candidate.get("currency_code")
        if isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
            return amount, currency.strip().upper()
    return None


def _candidate_label(artifact: str, candidate: dict[str, Any]) -> str:
    if artifact == "flights":
        airline = candidate.get("airline") or candidate.get("carrier")
        number = candidate.get("flight_number") or candidate.get("flightNumber")
        label = " ".join(str(x) for x in (airline, number) if x)
        segments = _list(candidate.get("segments"))
        first = _dict(segments[0]) if segments else {}
        last = _dict(segments[-1]) if segments else {}
        route = " → ".join(str(x) for x in (first.get("origin"), last.get("destination")) if x)
        return " — ".join(x for x in (label or "Flight candidate", route) if x)
    if artifact == "hotels":
        return str(candidate.get("name") or candidate.get("hotel_name") or "Hotel candidate")
    return str(candidate.get("name") or candidate.get("title") or artifact.rstrip("s").title() + " candidate")


def _booking_records(mission: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    confirmed = []
    for item in _list(mission.get("confirmed_bookings")):
        if not isinstance(item, dict):
            continue
        if (
            item.get("status") == "confirmed_by_user"
            and item.get("confirmation_state") == "user_confirmed_from_email"
            and item.get("confirmation_method") == "explicit_user_action"
        ):
            confirmed.append(item)
    pending = [
        item for item in _list(mission.get("booking_evidence"))
        if isinstance(item, dict) and item.get("status") == "needs_user_review"
    ]
    return confirmed, pending


def _booking_summary(mission: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    confirmed, pending = _booking_records(mission)
    selections = _dict(mission.get("selections"))
    selected_lines = []
    for key, label in (("flights", "Flight"), ("hotels", "Hotel"), ("transfers", "Transfer")):
        record = _dict(selections.get(key))
        if record:
            candidate = _dict(record.get("candidate"))
            selected_lines.append(
                f"{label}: {_candidate_label(key, candidate)} — selected for planning, NOT BOOKED."
            )
    lines = [
        "Booking ledger (saved mission only):",
        "No booking execution or provider-side booking confirmation is recorded unless listed below.",
    ]
    lines.extend(selected_lines or ["No flight, hotel or transfer selection is recorded."])
    if confirmed:
        lines.append("User-reviewed Gmail confirmation candidates recorded as confirmed:")
        for item in confirmed:
            lines.append(
                "- " + " | ".join(str(item.get(field) or "not recorded") for field in ("subject", "from", "received_at", "message_id"))
            )
            lines.append("  User confirmed this email candidate; provider-side independent verification is NOT recorded.")
    else:
        lines.append("No user-confirmed booking evidence is recorded in this mission.")
    if pending:
        lines.append(f"{len(pending)} Gmail confirmation candidate(s) still require your review; none is treated as booked.")
    facts = {
        "selected_options": {
            key: {
                "label": _candidate_label(key, _dict(_dict(selections.get(key)).get("candidate"))),
                "status": _dict(selections.get(key)).get("selection_status") or "selected_not_booked",
            }
            for key in ("flights", "hotels", "transfers") if _dict(selections.get(key))
        },
        "confirmed_by_user_email_candidates": [
            {"message_id": item.get("message_id"), "subject": item.get("subject"), "sender": item.get("from"), "received_at": item.get("received_at"), "provider_independently_verified": False}
            for item in confirmed
        ],
        "pending_email_candidates": [
            {"message_id": item.get("message_id"), "subject": item.get("subject"), "sender": item.get("from"), "received_at": item.get("received_at"), "status": "needs_user_review"}
            for item in pending
        ],
        "warik_booking_action_recorded": False,
        "provider_booking_status_independently_verified": False,
        "booking_status": "user_confirmed_email_evidence_present" if confirmed else "no_confirmation_recorded",
    }
    return "\n".join(lines), facts


def _provenance(mission: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    artifacts = _dict(mission.get("artifacts"))
    lines = ["Travel evidence provenance (from stored mission records):"]
    facts: dict[str, Any] = {}
    if not artifacts:
        lines.append("No travel artifact evidence is recorded.")
    for name in ("flights", "hotels", "transfers", "routes", "itinerary", "budget"):
        record = _dict(artifacts.get(name))
        if not record:
            facts[name] = {"status": "not_recorded"}
            continue
        evidence = _dict(record.get("evidence"))
        verified = _is_verified_live_artifact(record)
        provider_recorded = record.get("provider")
        provider = provider_recorded if verified and provider_recorded else None
        retrieved_at = record.get("retrieved_at") if verified else None
        status = _artifact_status(name, record)
        facts[name] = {
            "status": status,
            "provider": provider,
            "provider_label_unverified": provider_recorded if provider_recorded and not verified else None,
            "source_type": record.get("source_type"),
            "retrieved_at": retrieved_at,
            "live_inventory": evidence.get("live_inventory"),
            "candidate_count": evidence.get("candidate_count"),
            "search_url": evidence.get("search_url"),
            "tool_name": evidence.get("tool_name"),
        }
        provider_text = str(provider) if provider else "not independently attributable"
        timestamp_text = str(retrieved_at) if retrieved_at else "not recorded/verified"
        lines.append(
            f"- {name}: status={status}; provider={provider_text}; source={record.get('source_type') or 'unknown'}; provider retrieval time={timestamp_text}; candidates={evidence.get('candidate_count', len(_list(_dict(mission.get('candidates')).get(name))))}."
        )
        if evidence.get("live_inventory") is False:
            lines.append("  Provider/tool record explicitly says live inventory was not queried or was unavailable.")
        if name in {"flights", "hotels"} and record.get("status") == "current" and not verified:
            lines.append("  Legacy record lacks explicit provider-attribution and provider-timestamp verification flags; it is not treated as verified live evidence.")
        if record.get("source_type") == "external_handoff":
            lines.append("  This is a handoff, not live inventory and not a booking.")
    return "\n".join(lines), facts


def _queue(mission: dict[str, Any], state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    entries = [item for item in _list(mission.get("pending_recalculations")) if isinstance(item, dict)]
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in ("pending", "blocked", "deferred", "running", "awaiting_approval")}
    report = _dict(state.get("last_travel_recalculation"))
    deferred = report.get("status") == "deferred"
    for item in entries:
        status = str(item.get("status") or "pending").lower()
        if deferred and status in {"pending", "dispatching", "running"}:
            groups["deferred"].append(item)
        elif status in groups:
            groups[status].append(item)
        elif status in {"dispatching", "in_progress", "in-progress"}:
            groups["running"].append(item)
    artifacts = _dict(mission.get("artifacts"))
    completed = []
    stale = []
    for name, record_value in artifacts.items():
        record = _dict(record_value)
        if _artifact_status(str(name), record) == "current":
            completed.append(str(name))
        elif str(record.get("status") or "").lower() == "stale":
            stale.append(str(name))
    lines = ["Travel recalculation state (persisted queue only):"]
    for name in ("completed evidence", "stale artifacts", "pending", "deferred", "running", "awaiting approval", "blocked"):
        values = completed if name == "completed evidence" else stale if name == "stale artifacts" else groups.get(name.replace(" ", "_"), [])
        if name in {"pending", "deferred", "running", "awaiting approval", "blocked"}:
            rendered = [f"{item.get('artifact') or 'task'} ({item.get('queue_id') or 'no queue id'}): {item.get('blocked_reason') or item.get('reason') or item.get('status') or 'status not recorded'}" for item in values]
        else:
            rendered = values
        lines.append(f"- {name.title()}: {', '.join(rendered) if rendered else 'None recorded'}")
    if deferred:
        lines.append("Latest dispatcher report says work was deferred because another workflow was active; this is not evidence that a provider search completed.")
    elif report:
        lines.append(f"Latest dispatcher report status: {report.get('status') or 'not recorded'}; workflow id: {report.get('workflow_id') or 'not recorded'}.")
    return "\n".join(lines), {
        "completed_evidence_artifacts": completed,
        "stale_artifacts": stale,
        **{key: [{"artifact": x.get("artifact"), "queue_id": x.get("queue_id"), "reason": x.get("blocked_reason") or x.get("reason"), "status": x.get("status")} for x in values] for key, values in groups.items()},
        "last_dispatch_status": report.get("status"),
        "last_dispatch_workflow_id": report.get("workflow_id"),
    }


def _options(mission: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    candidates_by_artifact = _dict(mission.get("candidates"))
    artifacts = _dict(mission.get("artifacts"))
    selections = _dict(mission.get("selections"))
    lines = ["Options stored in the current travel mission:"]
    facts: dict[str, Any] = {"options": {}, "external_handoffs": []}
    for artifact in ("flights", "hotels", "transfers"):
        candidates = [item for item in _list(candidates_by_artifact.get(artifact)) if isinstance(item, dict)]
        if not candidates:
            continue
        record = _dict(artifacts.get(artifact))
        verified = _is_verified_live_artifact(record)
        selection = _dict(selections.get(artifact))
        selected_candidate = _dict(selection.get("candidate"))
        facts["options"][artifact] = []
        lines.append(f"{artifact.title()} ({_artifact_status(artifact, record)}):")
        for index, candidate in enumerate(candidates, start=1):
            is_selected = bool(selected_candidate and candidate == selected_candidate)
            if candidate.get("kind") == "external_handoff":
                handoff = {
                    "artifact": artifact,
                    "status": "external_handoff_not_booked",
                    "links_recorded": bool(candidate.get("links")),
                    "validated": False,
                }
                facts["external_handoffs"].append(handoff)
                label = "External handoff recorded; link not yet validated; not booked."
            else:
                label = _candidate_label(artifact, candidate)
            provenance = "provider-attributed live result" if verified else "stored candidate with unverified source/freshness"
            state_label = "SELECTED — NOT BOOKED" if is_selected else "recommendation only"
            lines.append(f"- Option {index}: {label}; {state_label}; {provenance}.")
            facts["options"][artifact].append({
                "option": index,
                "label": label,
                "selected": is_selected,
                "status": "selected_not_booked" if is_selected else "recommendation_only",
                "source_verified": verified,
            })
    if not facts["options"]:
        lines.append("No flight, hotel or transfer candidates are stored.")
    lines.append("No option or handoff is a reservation or completed booking.")
    return "\n".join(lines), facts


def _feasibility(mission: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # Re-evaluate a sanitized copy. Legacy flight/hotel artifacts cannot make
    # a PASS because their old provider/timestamp labels were not attested.
    safe = deepcopy(mission)
    artifacts = _dict(safe.get("artifacts"))
    for name in ("flights", "hotels"):
        record = _dict(artifacts.get(name))
        if record.get("status") == "current" and not _is_verified_live_artifact(record):
            record["status"] = "stale"
    from app.services.context.travel_feasibility import evaluate_travel_feasibility
    result = evaluate_travel_feasibility(safe)
    checks = _list(result.get("checks"))
    lines = [f"Current evidence-aware feasibility: {result.get('status') or 'UNKNOWN'}."]
    for item in checks:
        if isinstance(item, dict):
            lines.append(f"- {item.get('id')}: {item.get('status', 'UNKNOWN')} — {item.get('detail', 'No detail recorded.')}")
    return "\n".join(lines), result


def _cost(mission: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    lines = ["Trip cost evidence (unknown values are not replaced with zero):"]
    parts: dict[str, Any] = {}
    for name, keys, label in (
        ("flights", ("price_amount", "total_amount"), "Selected flight"),
        ("hotels", ("total_stay_amount", "total_amount", "total_inr"), "Selected hotel stay"),
    ):
        selection = _selected(mission, name)
        if not selection:
            parts[name] = {"status": "unknown", "amount": None, "currency": None}
            lines.append(f"- {label}: UNKNOWN — no selected candidate recorded.")
            continue
        artifact = _dict(_dict(mission.get("artifacts")).get(name))
        if not _is_verified_live_artifact(artifact):
            parts[name] = {"status": "unknown_unverified_evidence", "amount": None, "currency": None}
            lines.append(f"- {label}: UNKNOWN — selected option exists, but current provider evidence is not verified.")
            continue
        money = _money(_dict(selection.get("candidate")), keys)
        if money is None:
            parts[name] = {"status": "unknown_missing_numeric_price_or_currency", "amount": None, "currency": None}
            lines.append(f"- {label}: UNKNOWN — provider did not supply both a numeric amount and ISO currency.")
            continue
        amount, currency = money
        basis = "total stay" if name == "hotels" else str(_dict(artifact.get("evidence")).get("price_basis") or "provider quote basis not specified")
        parts[name] = {"status": "provider_reported", "amount": amount, "currency": currency, "price_basis": basis}
        lines.append(f"- {label}: {amount:,.2f} {currency} ({basis}; not a booking).")
    lines.append("- Airport transfer: UNKNOWN — a handoff link or route estimate is not a quoted ride fare.")
    lines.append("- Food, activities and miscellaneous expenses: UNKNOWN unless explicit estimates are stored in mission preferences.")
    lines.append("- Reliable total: UNKNOWN — the complete trip cost and comparable quote basis are not established.")
    return "\n".join(lines), {"components": parts, "transfer": {"status": "unknown", "amount": None}, "other_expenses": "unknown", "total": None}


def _summary(mission: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    constraints = _constraints(mission)
    lines = ["Saved travel mission constraints:"]
    lines.extend([f"- {key}: {value}" for key, value in constraints.items()] or ["- No explicit trip constraints recorded."])
    preferences = _dict(mission.get("preferences"))
    lines.append("Preferences:")
    lines.extend([f"- {key}: {value}" for key, value in preferences.items()] or ["- No explicit preferences recorded."])
    for name, label in (("flights", "Flight"), ("hotels", "Hotel")):
        selection = _selected(mission, name)
        if selection:
            candidate = _dict(selection.get("candidate"))
            lines.append(f"{label} selection: {_candidate_label(name, candidate)} — selected, not booked.")
        else:
            lines.append(f"{label} selection: none recorded.")
    return "\n".join(lines), {"constraints": constraints, "preferences": preferences}


def build_travel_mission_read_response(conversation: Any, text: str) -> AgentMessageResponse | None:
    """Return a deterministic response for travel ledger/provenance questions.

    ``None`` means the user request is not a local mission read and should
    continue through normal routing (including real provider/connector actions).
    """
    intent = _intent_for(text)
    if intent is None:
        return None
    state = _dict(getattr(conversation, "state_json", None))
    raw = state.get(MISSION_KEY)
    if not isinstance(raw, dict):
        return AgentMessageResponse(
            reply=(
                "I don't have a valid saved travel mission and evidence ledger for this conversation. "
                "I cannot verify providers, prices, recalculation outcomes or bookings from chat history, "
                "so those details remain UNKNOWN. No booking is confirmed by this response."
            ),
            structured_data={"type": "travel_mission_read", "intent": intent, "mission_available": False, "status": "UNKNOWN"},
        )
    try:
        mission = TravelMission.model_validate(raw)
    except Exception:
        return AgentMessageResponse(
            reply=(
                "The saved travel mission failed schema validation. I will not reconstruct it from chat history "
                "or make provider, cost or booking claims. Its status is UNKNOWN until the stored state is repaired."
            ),
            structured_data={"type": "travel_mission_read", "intent": intent, "mission_available": True, "status": "INVALID_STORED_STATE"},
        )

    data = mission.model_dump(mode="json")
    if intent == "bookings":
        reply, facts = _booking_summary(data)
    elif intent == "options":
        reply, facts = _options(data)
    elif intent == "provenance":
        reply, facts = _provenance(data)
    elif intent == "queue":
        reply, facts = _queue(data, state)
    elif intent == "feasibility":
        reply, facts = _feasibility(data)
    elif intent == "cost":
        reply, facts = _cost(data)
    elif intent == "summary":
        reply, facts = _summary(data)
    else:
        summary, summary_facts = _summary(data)
        booking_text, booking_facts = _booking_summary(data)
        provenance_text, provenance_facts = _provenance(data)
        queue_text, queue_facts = _queue(data, state)
        feasibility_text, feasibility_facts = _feasibility(data)
        cost_text, cost_facts = _cost(data)
        reply = "\n\n".join((
            f"TRAVEL MISSION AUDIT — mission {data.get('mission_id')} / version {data.get('version')}\n{summary}",
            booking_text,
            provenance_text,
            queue_text,
            feasibility_text,
            cost_text,
            "Important: only records stored in this mission are reported. Missing provider evidence is UNKNOWN; a selected option, recommendation or external handoff is not a booking.",
        ))
        facts = {
            "summary": summary_facts,
            "bookings": booking_facts,
            "provenance": provenance_facts,
            "queue": queue_facts,
            "feasibility": feasibility_facts,
            "cost": cost_facts,
        }
    return AgentMessageResponse(
        reply=reply,
        structured_data={
            "type": "travel_mission_read",
            "intent": intent,
            "mission_available": True,
            "mission_id": data.get("mission_id"),
            "mission_version": data.get("version"),
            "facts": facts,
        },
    )
