"""Fast, deterministic intent and argument extraction for the most common
phrasings. Runs before the LLM so the app remains usable with no LLM configured.
"""

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

_CURRENCY = r"(?:₹|rs\.?|inr|rupees?)"

_CATEGORY_KEYWORDS = {
    "Food": ["lunch", "dinner", "breakfast", "food", "restaurant", "cafe", "coffee", "tea", "snack", "meal", "biryani", "pizza"],
    "Transport": ["taxi", "uber", "ola", "auto", "rickshaw", "bus", "train", "metro", "fuel", "petrol", "diesel", "cab"],
    "Groceries": ["grocery", "groceries", "vegetables", "milk", "bread", "rice", "flour"],
    "Shopping": ["shopping", "clothes", "shirt", "shoes", "amazon", "flipkart"],
    "Entertainment": ["movie", "cinema", "netflix", "spotify", "game", "concert"],
    "Health": ["medicine", "doctor", "pharmacy", "hospital", "gym"],
    "Education": ["book", "course", "tuition", "class", "exam", "stationery"],
    "Utilities": ["electricity", "water", "internet", "mobile", "recharge", "bill"],
}

_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_RELATIVE_RE = re.compile(r"\bin\s+(\d+)\s+(minute|min|hour|hr|day)s?\b", re.IGNORECASE)

_EXPENSE_RE = re.compile(
    rf"(?:spent|paid|bought|cost)\s+(?:{_CURRENCY}\s*)?(\d+(?:[.,]\d{{1,2}})?)",
    re.IGNORECASE,
)
_EXPENSE_ALT_RE = re.compile(
    rf"{_CURRENCY}\s*(\d+(?:[.,]\d{{1,2}})?)",
    re.IGNORECASE,
)

_REMINDER_REL_RE = re.compile(
    r"remind\s+me(?:\s+to)?\s+(.+?)\s+(in\s+\d+\s+(?:minute|min|hour|hr|day)s?)\b",
    re.IGNORECASE,
)
_REMINDER_ABS_RE = re.compile(
    r"remind\s+me(?:\s+to)?\s+(.+?)\s+\b(?:at|by)\b\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_REMIND_ME_ONLY_RE = re.compile(r"^remind\s+me(?:\s+to)?\s+(.+)$", re.IGNORECASE)

_TASK_RE = re.compile(
    r"(?:add(?:\s+a)?\s+task(?:\s+to)?|create\s+task(?:\s+to)?)\s+(.+)",
    re.IGNORECASE,
)

_SUMMARY_PATTERNS = [
    (re.compile(r"this\s+month|monthly", re.IGNORECASE), "month"),
    (re.compile(r"this\s+week|weekly", re.IGNORECASE), "week"),
    (re.compile(r"\btoday\b|daily|so\s+far\s+today", re.IGNORECASE), "today"),
]


def _detect_category(text: str) -> str:
    low = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(k in low for k in keywords):
            return category
    return "Other"


def _parse_time_of_day(text: str, ref: datetime) -> Optional[datetime]:
    match = _TIME_RE.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    ampm = (match.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm and 0 < hour <= 7:
        hour += 12  # 7 → 19:00; small bare hours are evening for reminders
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return None
    target = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= ref:
        target += timedelta(days=1)
    return target


def _parse_reminder_when(text: str, ref: datetime) -> Optional[datetime]:
    relative = _RELATIVE_RE.search(text)
    if relative:
        n = int(relative.group(1))
        unit = relative.group(2).lower()
        if unit.startswith("min"):
            return ref + timedelta(minutes=n)
        if unit.startswith("hour") or unit == "hr":
            return ref + timedelta(hours=n)
        if unit.startswith("day"):
            return ref + timedelta(days=n)

    base = ref
    low = text.lower()
    if "tomorrow" in low:
        base = ref + timedelta(days=1)
    return _parse_time_of_day(text, base)


def _try_parse_expense(text: str) -> Optional[dict]:
    match = _EXPENSE_RE.search(text) or _EXPENSE_ALT_RE.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", ".")
    try:
        amount = Decimal(raw)
    except Exception:  # noqa: BLE001
        return None
    if amount <= 0:
        return None

    desc_match = re.search(r"\b(?:on|for)\s+(.+?)(?:\.|$)", text, re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else None
    category = _detect_category(description or text)

    params = {"amount": str(amount), "category": category}
    if description:
        params["description"] = description
    return {"intent": "add_expense", "params": params}


def _try_parse_reminder(text: str, ref: datetime) -> Optional[dict]:
    for pattern in (_REMINDER_REL_RE, _REMINDER_ABS_RE):
        match = pattern.search(text)
        if not match:
            continue
        title = match.group(1).strip()
        when_text = match.group(2).strip()
        when = _parse_reminder_when(when_text, ref)
        if when is not None and title:
            return {
                "intent": "create_reminder",
                "params": {"title": title, "remind_at": when.isoformat()},
            }
    return None


def _try_parse_summary(text: str) -> Optional[dict]:
    has_how_much = re.search(
        r"(how\s+much|total|summary|what\s+did\s+i\s+spen[dt])",
        text,
        re.IGNORECASE,
    )
    has_spend_word = re.search(r"spen[dt]|expense|expenses", text, re.IGNORECASE)
    if not (has_how_much and has_spend_word):
        return None
    period = "today"
    for pattern, name in _SUMMARY_PATTERNS:
        if pattern.search(text):
            period = name
            break
    return {"intent": "calculate_expense_summary", "params": {"period": period}}


def parse(text: str, ref: Optional[datetime] = None) -> Optional[dict]:
    if not text or not text.strip():
        return None

    now = ref or datetime.now()
    t = text.strip()

    # Order matters: summary before add-expense so "how much did I spend" is a question.
    route = _try_parse_summary(t)
    if route is not None:
        return route

    route = _try_parse_expense(t)
    if route is not None:
        return route

    route = _try_parse_reminder(t, now)
    if route is not None:
        return route

    task_match = _TASK_RE.search(t)
    if task_match:
        title = task_match.group(1).strip()
        if title:
            return {"intent": "create_task", "params": {"title": title}}

    remind_only = _REMIND_ME_ONLY_RE.match(t)
    if remind_only:
        title = remind_only.group(1).strip()
        if title:
            return {"intent": "create_task", "params": {"title": title}}

    if re.search(r"plan\s+my\s+day", t, re.IGNORECASE):
        params = {}
        if re.search(r"\btomorrow\b", t, re.IGNORECASE):
            params["due_on"] = (now.date() + timedelta(days=1)).isoformat()
        elif re.search(r"\btoday\b", t, re.IGNORECASE):
            params["due_on"] = now.date().isoformat()
        return {"intent": "list_tasks", "params": params}

    return None