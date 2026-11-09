import re
from datetime import datetime, timedelta
from typing import Optional

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "couple": 2, "pair": 2, "single": 1,
}

def _normalize_people(text: str) -> Optional[int]:
    low = text.lower()
    if re.search(r"\bmy\s+parents\s+and\s+i\b", low): return 3
    if re.search(r"\bmy\s+parents\b", low): return 2
    if re.search(r"\bmy\s+(?:wife|husband|partner|friend|son|daughter)\b", low): return 2
    if re.search(r"\bme\s+and\s+my\s+(?:friend|wife|husband|partner)\b", low): return 2

    for pattern in (
        r"\bfor\s+(\w+)\s+(?:people|persons|travellers|travelers|adults|guests|pax)\b",
        r"\b(\w+)\s+(?:people|persons|travellers|travelers|adults|guests|pax)\b",
    ):
        m = re.search(pattern, low)
        if m:
            token = m.group(1).strip()
            if token.isdigit() and 1 <= int(token) <= 20: return int(token)
            if token in WORD_NUMBERS: return WORD_NUMBERS[token]

    m = re.search(r"\bfor\s+(\w+)\s*$", low)
    if m:
        token = m.group(1).strip()
        if token.isdigit() and 1 <= int(token) <= 20: return int(token)
        if token in WORD_NUMBERS: return WORD_NUMBERS[token]
    return None

def _parse_date(text: str, ref: datetime) -> Optional[str]:
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    text = text.lower()
    match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{4})?", text)
    if not match:
        match = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})?", text)
        if match:
            month_str, mday, year_str = match.group(1)[:3], match.group(2), match.group(3)
        else: return None
    else:
        mday, month_str, year_str = match.group(1), match.group(2)[:3], match.group(3)
    month = months.get(month_str)
    if not month: return None
    year = int(year_str) if year_str else ref.year
    try: return datetime(year, month, int(mday)).strftime("%Y-%m-%d")
    except Exception: return None

def _try_parse_expense(text: str) -> Optional[dict]:
    """Parse simple expense statements into the add_expense tool format."""
    match = re.search(
        r"\b(?:spent|paid| खर्च)\s*(?:₹|rs\.?|inr)?\s*"
        r"(\d+(?:\.\d{1,2})?)\s*(?:rupees?|rs\.?|inr)?"
        r"(?:\s+(?:on|for)\s+(.+))?",
        text,
        re.IGNORECASE,
    )
    if not match:
        # Also support: "I spent 250 on lunch"
        match = re.search(
            r"\b(?:spent|paid)\s+"
            r"(\d+(?:\.\d{1,2})?)\s*(?:rupees?|rs\.?|inr)?"
            r"(?:\s+(?:on|for)\s+(.+))?",
            text,
            re.IGNORECASE,
        )

    if not match:
        return None

    amount = match.group(1)
    description_match = re.search(
    r"\b(?:on|for)\s+(.+)$",
    text,
    re.IGNORECASE,
)

    description = (
    description_match.group(1).strip(" .?!")
    if description_match
    else (match.group(2) or "Expense").strip(" .?!")
)

    low_description = description.lower()

    low_description = description.lower()

    if re.search(
        r"\b(lunch|dinner|breakfast|food|restaurant|coffee|"
        r"pizza|biryani|snack|meal|groceries)\b",
        low_description,
    ):
        category = "Food"
    elif re.search(
        r"\b(petrol|diesel|fuel|cab|taxi|uber|ola|bus|"
        r"train|metro|transport|auto)\b",
        low_description,
    ):
        category = "Transport"
    else:
        category = "Other"

    return {
        "intent": "add_expense",
        "params": {
            "amount": amount,
            "category": category,
            "description": description,
        },
    }


def _try_parse_reminder(text: str, ref: datetime) -> Optional[dict]:
    """Parse relative and clock-time reminders."""
    match = re.search(
        r"\bremind\s+me\s+to\s+(.+)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    remainder = match.group(1).strip().rstrip(" .?!")
    remind_at = None

    # Relative reminder: in 30 minutes / in 2 hours / in 3 days
    relative = re.search(
        r"\s+in\s+(\d+)\s+(minutes?|mins?|hours?|hrs?|days?)\b",
        remainder,
        re.IGNORECASE,
    )

    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()

        if unit.startswith(("minute", "min")):
            delta = timedelta(minutes=amount)
        elif unit.startswith(("hour", "hr")):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)

        remind_at = ref + delta
        title = remainder[:relative.start()].strip()
    else:
        # Absolute clock time: at 7 PM / at 7:30 AM
        clock = re.search(
            r"\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
            remainder,
            re.IGNORECASE,
        )

        if not clock:
            return None

        hour = int(clock.group(1))
        minute = int(clock.group(2) or 0)
        meridiem = clock.group(3).lower()

        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return None

        hour = hour % 12
        if meridiem == "pm":
            hour += 12

        remind_at = ref.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        # If the requested time has already passed, schedule tomorrow.
        if remind_at <= ref:
            remind_at += timedelta(days=1)

        title = remainder[:clock.start()].strip()

    if not title or remind_at is None:
        return None

    return {
        "intent": "create_reminder",
        "params": {
            "title": title,
            "remind_at": remind_at.isoformat(),
        },
    }


def _try_parse_task(text: str) -> Optional[dict]:
    """Parse explicit task-creation requests."""
    match = re.search(
        r"\b(?:add|create|make)\s+(?:a\s+)?task\s+"
        r"(?:to\s+)?(.+)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    title = match.group(1).strip().rstrip(" .?!")
    if not title:
        return None

    return {
        "intent": "create_task",
        "params": {
            "title": title,
        },
    }


def _try_parse_expense_summary(text: str) -> Optional[dict]:
    """Parse requests for deterministic expense summaries."""
    low = text.lower()

    if not re.search(
        r"\b(spent|spending|expenses?|expense|"
        r"how much did i spend)\b",
        low,
    ):
        return None

    if re.search(r"\b(this week|weekly|last week)\b", low):
        period = "week"
    elif re.search(r"\b(this month|monthly|last month)\b", low):
        period = "month"
    elif re.search(r"\b(today|daily|this day)\b", low):
        period = "day"
    else:
        return None

    return {
        "intent": "calculate_expense_summary",
        "params": {
            "period": period,
        },
    }

def _extract_budget(text: str) -> Optional[float]:
    low = text.lower().replace(",", "")
    m = re.search(r"(?:under|below|within|budget|max|upto|up to|of)\s*[₹rs.\s]*(\d+(?:\.\d+)?)\s*(k|thousand)?", low)
    if m:
        value = float(m.group(1))
        if m.group(2): value *= 1000
        if value >= 100: return value
    return None

def _extract_nights(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*nights?", text, re.IGNORECASE)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*days?", text, re.IGNORECASE)
    if m: return max(1, int(m.group(1)) - 1) if "trip" in text.lower() else int(m.group(1))
    return None

def _extract_travellers(text: str) -> int:
    low = text.lower()
    for phrase, num in [("a couple", 2), ("a pair", 2)]:
        if re.search(rf"\bfor\s+{re.escape(phrase)}\b", low): return num
    for pattern in (
        r"\bfor\s+(\w+)\s+(?:people|persons|travellers|travelers|adults|guests|pax)\b",
        r"\b(\w+)\s+(?:people|persons|travellers|travelers|adults|guests|pax)\b",
        r"\bfor\s+(\w+)\b" # e.g. "for 2"
    ):
        m = re.search(pattern, low)
        if m:
            token = m.group(1).strip()
            if token.isdigit():
                n = int(token)
                if 1 <= n <= 20: return n
            if token in WORD_NUMBERS: return min(WORD_NUMBERS[token], 20)
    return 1

def _try_parse_trip(text: str) -> Optional[dict]:
    # CRITICAL FIX: Do not parse a single word (like "Mumbai") as a trip.
    if not re.search(r"\d+[- ]day|trip|itinerary|vacation|holiday", text, re.IGNORECASE):
        return None

    days = 3
    m = re.search(r"(\d+)[- ]days?", text, re.IGNORECASE)
    if m: days = int(m.group(1))

    budget = _extract_budget(text)
    travellers = _extract_travellers(text)
    include_hotels = bool(re.search(r"with hotels", text, re.IGNORECASE))

    check_in, check_out = None, None
    date_m = re.search(r"from\s+(\d{1,2}\s+[a-zA-Z]+)\s+to\s+(\d{1,2}\s+[a-zA-Z]+(?:\s+\d{4})?)", text, re.IGNORECASE)
    if date_m:
        check_in = _parse_date(date_m.group(1), datetime.now())
        check_out = _parse_date(date_m.group(2), datetime.now())

    cleaned = text
    cleaned = re.sub(r"\b\d+[- ]days?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:plan|make|create|build|a|an|the|my|me|please|want|need)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:under|below|within|max|upto|up\s+to|budget(?:\s+of)?)\s*[₹rs.\s]*\d+(?:\.\d+)?\s*(?:k|thousand)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfor\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|couple|pair|a\s+couple|a\s+pair)(?:\s+(?:people|persons|travellers|travelers|adults|guests|pax))?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfrom\s+\d{1,2}\s+[a-zA-Z]+\s+to\s+\d{1,2}\s+[a-zA-Z]+(?:\s+\d{4})?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:trip|itinerary|vacation|holiday|tour|travel|with\s+hotels|with\s+flights|with\s+food)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdays?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")

    if not cleaned or len(cleaned) < 3: return None

    origin, destination = None, None

    m = re.search(r"\bfrom\s+([A-Za-z][A-Za-z\s]+?)\s+to\s+([A-Za-z][A-Za-z\s,]+)$", cleaned, re.IGNORECASE)
    if m: origin, destination = m.group(1).strip(), m.group(2).strip()
    if not destination:
        m = re.search(r"^([A-Za-z][A-Za-z\s,]+?)\s+from\s+([A-Za-z][A-Za-z\s]+)$", cleaned, re.IGNORECASE)
        if m: destination, origin = m.group(1).strip(), m.group(2).strip()
    if not destination:
        m = re.search(r"\b(?:across|covering)\s+(.+)$", cleaned, re.IGNORECASE)
        if m: destination = m.group(1).strip()
    if not destination:
        m = re.search(r"\b(?:to|in)\s+([A-Za-z][A-Za-z\s,]+)$", cleaned, re.IGNORECASE)
        if m: destination = m.group(1).strip()
    if not destination and cleaned:
        destination = cleaned.strip()

    if not destination: return None

    destination = re.sub(r"\s+covering\s+", ", ", destination, flags=re.IGNORECASE)
    destination = re.sub(r"\s+and\s+", ", ", destination, flags=re.IGNORECASE)
    destination = re.sub(r"\s+to\s+", ", ", destination, flags=re.IGNORECASE)
    destination = destination.strip(" ,.-")

    if not destination: return None

    params: dict = {"days": days, "destination": destination, "travellers": travellers, "include_hotels": include_hotels}
    if budget is not None: params["budget"] = budget
    if origin: params["origin"] = origin.strip()
    if check_in: params["check_in"] = check_in
    if check_out: params["check_out"] = check_out

    return {"intent": "generate_advanced_itinerary", "params": params}

def _try_parse_food(text: str) -> Optional[dict]:
    low = text.lower()
    food_keywords = ["hungry", "eat", "food", "khana", "restaurant", "cafe", "coffee", "biryani", "pizza", "momos", "dosa", "chinese", "thali", "vegetarian", "veg", "non-veg", "spicy", "healthy"]
    if not any(k in low for k in food_keywords) and len(text.split()) > 3: return None
    if len(text.split()) <= 2 and text[0].isupper() and not any(k in low for k in food_keywords):
        return {"intent": "discover_food", "params": {"location": text.strip(), "query": "restaurant"}}
    loc_match = re.search(r"(?:in|near|around)\s+([a-zA-Z\s]+)", text, re.IGNORECASE)
    location = loc_match.group(1).strip() if loc_match else ""
    location = re.sub(r"\b(on|for|with|under|below)\b.*", "", location, flags=re.IGNORECASE).strip()
    query = "restaurant"
    if "biryani" in low: query = "biryani"
    elif "pizza" in low: query = "pizza"
    elif "momos" in low: query = "momos"
    elif "dosa" in low: query = "dosa"
    elif "cafe" in low or "coffee" in low: query = "cafe"
    elif "vegetarian" in low or "veg" in low: query = "vegetarian restaurant"
    elif "spicy" in low: query = "spicy food"
    elif "healthy" in low: query = "healthy food"
    return {"intent": "discover_food", "params": {"location": location, "query": query}}

def _try_parse_hotel(text: str, ref: datetime) -> Optional[dict]:
    match = re.search(r"(?:hotels?|stays?|accommodation).*?(?:in|near)\s+([a-zA-Z]+)", text, re.IGNORECASE)
    if not match: return None
    city = match.group(1).strip()
    budget = _extract_budget(text)
    date_text = re.sub(r"(?:hotels?|stays?|accommodation).*?(?:in|near)\s+[a-zA-Z]+", "", text, flags=re.IGNORECASE)
    date_text = re.sub(r"under\s*[₹rs.]\s*\d+", "", date_text, flags=re.IGNORECASE)
    date_parts = re.split(r"\s+(?:to|until|till|-)\s+", date_text, flags=re.IGNORECASE)
    check_in = _parse_date(date_parts[-2], ref) if len(date_parts) >= 2 else _parse_date(date_text, ref)
    check_out = _parse_date(date_parts[-1], ref) if len(date_parts) >= 2 else None
    params = {"city": city}
    if budget: params["budget"] = budget
    if check_in: params["check_in"] = check_in
    if check_out: params["check_out"] = check_out
    return {"intent": "search_hotels_stayapi", "params": params}

def _try_parse_flight(text: str, ref: datetime) -> Optional[dict]:
    match = re.search(r"(?:flight|fly).*?from\s+([a-zA-Z]+)\s+to\s+([a-zA-Z]+)(?:\s+(?:on|for)\s+(.+))?$", text, re.IGNORECASE)
    if not match: return None
    date_str = match.group(3).strip() if match.group(3) else ""
    parsed_date = (ref + timedelta(days=1)).strftime("%Y-%m-%d")
    if date_str:
        extracted = _parse_date(date_str, ref)
        if extracted: parsed_date = extracted
    return {"intent": "search_flights_real", "params": {"origin": match.group(1).strip(), "destination": match.group(2).strip(), "date": parsed_date}}

def _try_parse_cab(text: str) -> Optional[dict]:
    match = re.search(r"(?:cab|taxi|auto|ola|uber).*?from\s+(.+?)\s+to\s+(.+)", text, re.IGNORECASE)
    if not match: return None
    return {"intent": "get_cab_links", "params": {"pickup_location": match.group(1).strip(), "dropoff_location": match.group(2).strip()}}

def parse(text: str, ref: Optional[datetime] = None) -> Optional[dict]:
    if not text or not text.strip(): return None
    now = ref or datetime.now()
    t = text.strip().replace(",", "")
        # Productivity and expense intents
    route = _try_parse_reminder(t, now)
    if route:
        return route

    route = _try_parse_task(t)
    if route:
        return route

    route = _try_parse_expense_summary(t)
    if route:
        return route

    route = _try_parse_expense(t)
    if route:
        return route

    explicit_trip = bool(re.search(r"\b(?:trip|itinerary|vacation|holiday)\b", t, re.IGNORECASE))

    if not explicit_trip:
        if re.search(r"\bhotels?\b|\bstays?\b|\baccommodation\b", t, re.IGNORECASE):
            route = _try_parse_hotel(t, now)
            if route: return route
        if re.search(r"\bflights?\b|\bfly\b", t, re.IGNORECASE):
            route = _try_parse_flight(t, now)
            if route: return route
        if re.search(r"\b(?:hungry|eat|food|khana|restaurant|cafe|coffee|biryani|pizza|momos|dosa|vegetarian|veg|spicy|healthy)\b", t, re.IGNORECASE):
            route = _try_parse_food(t)
            if route: return route
        if re.search(r"\bcab\b|\btaxi\b|\bauto\b|\bola\b|\buber\b", t, re.IGNORECASE):
            route = _try_parse_cab(t)
            if route: return route

    route = _try_parse_trip(t)
    if route: return route
    return None