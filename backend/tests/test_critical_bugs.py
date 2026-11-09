"""Regression tests for the 7 critical bugs."""
import pytest
from app.agents.budget_calculator import calculate_savings_plan
from app.agents.deterministic_parser import _normalize_people
from app.agents.orchestrator import _detect_hotel_date_conflict


def test_bug1_savings_plan_balances():
    """Bug 1: Budget must add up to income exactly."""
    plan = calculate_savings_plan(
        monthly_income=35000, rent=10000, food=6000, travel=3000
    )
    total = plan.total_expenses + plan.savings + plan.emergency_fund + plan.discretionary
    assert abs(total - 35000) < 0.01, f"Budget doesn't balance: {total} != 35000"
    assert plan.total_expenses == 19000, f"Expected 19000, got {plan.total_expenses}"


def test_bug1_overspending_detected():
    plan = calculate_savings_plan(monthly_income=20000, rent=15000, food=8000, travel=3000)
    assert len(plan.warnings) > 0
    assert "exceed" in plan.warnings[0].lower()


def test_bug2_parents_means_two():
    """Bug 2: 'My parents' → 2 travellers."""
    assert _normalize_people("My parents are visiting Mumbai") == 2


def test_bug2_parents_and_i_means_three():
    assert _normalize_people("My parents and I are visiting") == 3


def test_bug2_six_people():
    assert _normalize_people("Find a restaurant for six people") == 6


def test_bug3_conflicting_hotel_dates():
    """Bug 3: 8-13 Nov is 5 nights, user said 2."""
    entities = {
        "check_in": "2026-11-08",
        "check_out": "2026-11-13",
        "nights": 2,
    }
    has_conflict, msg = _detect_hotel_date_conflict(entities)
    assert has_conflict is True
    assert "5 nights" in msg
    assert "2 nights" in msg


def test_bug3_matching_dates_no_conflict():
    entities = {
        "check_in": "2026-11-08",
        "check_out": "2026-11-10",
        "nights": 2,
    }
    has_conflict, _ = _detect_hotel_date_conflict(entities)
    assert has_conflict is False