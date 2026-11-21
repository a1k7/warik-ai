"""Evidence-aware, conservative travel feasibility evaluation.

Only explicit numeric amounts with a known currency are summed. Missing prices,
provider durations, and incomplete cost categories remain UNKNOWN rather than 0.
This module has no provider calls and never claims to book or verify a reservation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status", "UNKNOWN")).upper() for item in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    return "PASS"


def _amount(candidate: Any, keys: tuple[str, ...]) -> float | None:
    if not isinstance(candidate, dict):
        return None
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            number = float(value)
            if number >= 0:
                return number
        if isinstance(value, str):
            raw = value.strip().replace(",", "")
            if re.fullmatch(r"\d+(?:\.\d{1,2})?", raw):
                number = float(raw)
                if number >= 0:
                    return number
    return None


def _currency(candidate: Any) -> str | None:
    if not isinstance(candidate, dict):
        return None
    value = candidate.get("currency") or candidate.get("currency_code")
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value.strip()):
        return value.strip().upper()
    return None


def _date_prefix(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    prefix = value[:10]
    try:
        return datetime.strptime(prefix, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _selection(mission: dict[str, Any], artifact: str) -> dict[str, Any] | None:
    item = (mission.get("selections") or {}).get(artifact)
    if not isinstance(item, dict) or not isinstance(item.get("candidate"), dict):
        return None
    artifact_state = (mission.get("artifacts") or {}).get(artifact) or {}
    if artifact_state.get("status") != "current":
        return None
    return item["candidate"]


def evaluate_travel_feasibility(mission_data: dict[str, Any]) -> dict[str, Any]:
    """Return PASS/WARNING/UNKNOWN/FAIL checks using only current evidence."""
    mission = mission_data if isinstance(mission_data, dict) else {}
    constraints = mission.get("constraints") or {}
    artifacts = mission.get("artifacts") or {}
    preferences = mission.get("preferences") or {}
    checks: list[dict[str, Any]] = []

    flight = _selection(mission, "flights")
    if flight is None:
        checks.append({"id": "selected_flight", "status": "UNKNOWN", "detail": "No current flight selection is available."})
    else:
        checks.append({"id": "selected_flight", "status": "PASS", "detail": "A flight candidate is selected; it is not booked."})

    hotel = _selection(mission, "hotels")
    if hotel is None:
        checks.append({"id": "selected_hotel", "status": "UNKNOWN", "detail": "No current hotel selection is available."})
    else:
        checks.append({"id": "selected_hotel", "status": "PASS", "detail": "A hotel candidate is selected; it is not reserved."})

    # Price evidence: do not parse display strings such as "₹5,250". The
    # normalizers should supply numeric price_amount / total_stay_amount fields.
    known_costs: list[dict[str, Any]] = []
    missing_costs: list[str] = []
    for label, candidate, keys in (
        ("flight", flight, ("price_amount", "total_amount")),
        ("hotel", hotel, ("total_stay_amount", "total_inr", "total_amount")),
    ):
        if candidate is None:
            missing_costs.append(label)
            continue
        amount = _amount(candidate, keys)
        currency = _currency(candidate)
        if amount is None or currency is None:
            missing_costs.append(label)
            checks.append({"id": f"{label}_price", "status": "UNKNOWN", "detail": "A numeric price and ISO currency were not both supplied."})
            continue
        known_costs.append({"component": label, "amount": amount, "currency": currency})
        checks.append({"id": f"{label}_price", "status": "PASS", "detail": f"Numeric provider/user price evidence is available in {currency}.", "amount": amount, "currency": currency})

    # Optional cost estimates count only when the application/user has stored
    # them explicitly as {amount: number, currency: ISO-4217}.
    estimates = preferences.get("cost_estimates") if isinstance(preferences, dict) else None
    if isinstance(estimates, dict):
        for label in ("food", "activities", "local_transport"):
            estimate = estimates.get(label)
            if estimate is None:
                missing_costs.append(label)
                continue
            amount = _amount(estimate, ("amount",))
            currency = _currency(estimate)
            if amount is None or currency is None:
                missing_costs.append(label)
                continue
            known_costs.append({"component": label, "amount": amount, "currency": currency})
    else:
        missing_costs.extend(["food", "activities", "local_transport"])

    currencies = sorted({item["currency"] for item in known_costs})
    subtotal = sum(item["amount"] for item in known_costs) if flight is not None and len(currencies) == 1 else None
    budget_amount = constraints.get("budget_amount")
    budget_currency = constraints.get("budget_currency")
    budget_check: dict[str, Any]
    if budget_amount is None or not budget_currency:
        budget_check = {"id": "budget", "status": "UNKNOWN", "detail": "A budget amount and currency are required for comparison."}
    elif not known_costs:
        budget_check = {"id": "budget", "status": "UNKNOWN", "detail": "No comparable selected travel costs are available."}
    elif len(currencies) != 1 or currencies[0] != str(budget_currency).upper():
        budget_check = {"id": "budget", "status": "UNKNOWN", "detail": "Cost currencies do not match the budget currency; no FX conversion was assumed.", "currencies": currencies, "budget_currency": str(budget_currency).upper()}
    elif subtotal is not None and subtotal > float(budget_amount):
        budget_check = {"id": "budget", "status": "FAIL", "detail": "Known selected costs already exceed the trip budget; additional costs are not included.", "known_subtotal": subtotal, "currency": currencies[0], "budget_amount": float(budget_amount)}
    elif missing_costs:
        budget_check = {"id": "budget", "status": "UNKNOWN", "detail": "Known subtotal is within budget, but the total trip cost is incomplete.", "known_subtotal": subtotal, "currency": currencies[0], "budget_amount": float(budget_amount), "missing_components": sorted(set(missing_costs))}
    else:
        budget_check = {"id": "budget", "status": "PASS", "detail": "All configured cost components are known and within budget.", "known_subtotal": subtotal, "currency": currencies[0], "budget_amount": float(budget_amount)}
    checks.append(budget_check)

    # Schedule consistency: segment times are provider-returned local strings.
    # Compare calendar dates only; never infer time zones or connection durations.
    if flight is not None:
        segments = flight.get("segments") or []
        first = segments[0] if segments and isinstance(segments[0], dict) else {}
        last = segments[-1] if segments and isinstance(segments[-1], dict) else {}
        departure_date = _date_prefix(first.get("departure"))
        arrival_date = _date_prefix(last.get("arrival"))
        planned_departure = constraints.get("departure_date")
        if planned_departure and departure_date:
            checks.append({"id": "flight_departure_date", "status": "PASS" if departure_date == planned_departure else "FAIL", "detail": "Selected flight departure date compared with the mission date.", "flight_date": departure_date, "mission_date": planned_departure})
        else:
            checks.append({"id": "flight_departure_date", "status": "UNKNOWN", "detail": "Departure date could not be compared with a specified mission date."})
        check_in = constraints.get("check_in")
        if hotel is not None and arrival_date and check_in:
            checks.append({"id": "arrival_before_hotel_checkin", "status": "FAIL" if arrival_date > check_in else "PASS", "detail": "Calendar-day arrival/check-in consistency check; local time zones are not inferred.", "arrival_date": arrival_date, "check_in": check_in})
        else:
            checks.append({"id": "arrival_before_hotel_checkin", "status": "UNKNOWN", "detail": "A selected hotel and comparable arrival/check-in dates are required."})
    else:
        checks.append({"id": "flight_schedule", "status": "UNKNOWN", "detail": "No current selected flight schedule is available."})

    route_artifact = artifacts.get("routes") or {}
    route_evidence = route_artifact.get("evidence") or {}
    route_source = str(route_artifact.get("source_type") or "")
    duration = route_evidence.get("travel_duration_minutes")
    road_distance = route_evidence.get("road_distance_km")
    if route_artifact.get("status") != "current":
        route_check = {"id": "route_timing", "status": "UNKNOWN", "detail": "No current route evidence is available."}
    elif isinstance(duration, (int, float)) and duration > 0 and isinstance(road_distance, (int, float)) and road_distance > 0 and route_source in {"provider_verified_route", "live_provider_route"}:
        route_check = {"id": "route_timing", "status": "PASS", "detail": "Provider-backed road distance and travel duration are available.", "road_distance_km": float(road_distance), "travel_duration_minutes": float(duration)}
    else:
        route_check = {"id": "route_timing", "status": "UNKNOWN", "detail": "Only straight-line estimates or incomplete route data are available; road duration remains unknown.", "road_distance_km": road_distance, "travel_duration_minutes": duration, "source_type": route_source or None}
    checks.append(route_check)

    pending = mission.get("pending_recalculations") or []
    if pending:
        checks.append({"id": "dependent_artifacts", "status": "WARNING", "detail": "Downstream results need recalculation after a selection or constraint change.", "pending_recalculations": [item.get("artifact") for item in pending if isinstance(item, dict)]})
    else:
        checks.append({"id": "dependent_artifacts", "status": "PASS", "detail": "No pending downstream recalculations are recorded."})

    return {
        "status": _status(checks),
        "evaluated_at": _now(),
        "mission_version": mission.get("version"),
        "known_costs": known_costs,
        "known_subtotal": subtotal,
        "known_subtotal_currency": currencies[0] if len(currencies) == 1 else None,
        "cost_completeness": "complete" if not missing_costs else "partial",
        "missing_cost_components": sorted(set(missing_costs)),
        "checks": checks,
        "pending_recalculations": [item for item in pending if isinstance(item, dict)],
        "booking_status": "not_inferred_from_search_or_itinerary",
    }
