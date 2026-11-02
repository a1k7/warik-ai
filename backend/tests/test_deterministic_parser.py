from datetime import datetime
from decimal import Decimal

from app.agents import deterministic_parser


def test_parse_expense_food():
    result = deterministic_parser.parse(
        "I spent ₹250 on lunch",
        ref=datetime(2026, 1, 15, 12, 0),
    )
    assert result is not None
    assert result["intent"] == "add_expense"
    assert Decimal(result["params"]["amount"]) == Decimal("250")
    assert result["params"]["category"] == "Food"
    assert "lunch" in (result["params"].get("description") or "")


def test_parse_expense_with_decimal_and_transport():
    result = deterministic_parser.parse(
        "I spent 180.50 rupees on petrol",
        ref=datetime(2026, 1, 15, 12, 0),
    )
    assert result is not None
    assert Decimal(result["params"]["amount"]) == Decimal("180.50")
    assert result["params"]["category"] == "Transport"


def test_parse_reminder_absolute():
    result = deterministic_parser.parse(
        "Remind me to study at 7 PM",
        ref=datetime(2026, 1, 15, 10, 0),
    )
    assert result is not None
    assert result["intent"] == "create_reminder"
    assert result["params"]["title"].lower().startswith("study")
    when = datetime.fromisoformat(result["params"]["remind_at"])
    assert when.hour == 19
    assert when.date() == datetime(2026, 1, 15).date()


def test_parse_reminder_relative():
    result = deterministic_parser.parse(
        "Remind me to call mom in 30 minutes",
        ref=datetime(2026, 1, 15, 10, 0),
    )
    assert result is not None
    when = datetime.fromisoformat(result["params"]["remind_at"])
    assert when == datetime(2026, 1, 15, 10, 30)


def test_parse_task():
    result = deterministic_parser.parse("Add a task to buy groceries")
    assert result is not None
    assert result["intent"] == "create_task"
    assert "groceries" in result["params"]["title"].lower()


def test_parse_summary_week():
    result = deterministic_parser.parse("How much did I spend this week?")
    assert result is not None
    assert result["intent"] == "calculate_expense_summary"
    assert result["params"]["period"] == "week"


def test_parse_unknown_returns_none():
    assert deterministic_parser.parse("Hello there, how are you?") is None