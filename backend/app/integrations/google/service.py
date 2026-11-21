"""Read-only Gmail search for user-authorized travel/food confirmations.

Only Gmail message metadata and the Gmail-provided short snippet are retrieved.
Message bodies are never requested and results are not persisted by this service.
"""

from datetime import datetime, timezone

import httpx

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
TRAVEL_CONTEXT_QUERY = (
    'newer_than:2y {flight airline hotel booking reservation itinerary '
    '"boarding pass" "e-ticket" cab taxi Uber Ola Swiggy Zomato}'
)


class GmailAPIError(RuntimeError):
    pass


def _category(subject: str, sender: str, snippet: str) -> str:
    text = f"{subject} {sender} {snippet}".casefold()
    if any(word in text for word in ("flight", "airline", "boarding pass", "e-ticket", "indigo", "air india", "spicejet")):
        return "flight"
    if any(word in text for word in ("hotel", "stay", "reservation", "check-in", "check in", "booking.com", "makemytrip")):
        return "hotel"
    if any(word in text for word in ("uber", "ola", "cab", "taxi", "ride receipt")):
        return "ground_transport"
    if any(word in text for word in ("swiggy", "zomato", "food order", "restaurant order")):
        return "food"
    return "other"


async def list_travel_confirmations(access_token: str, max_results: int = 20) -> dict:
    if not 1 <= max_results <= 25:
        raise ValueError("max_results must be between 1 and 25.")
    headers = {"Authorization": f"Bearer {access_token}"}
    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        try:
            listed = await client.get(
                f"{GMAIL_API}/messages",
                headers=headers,
                params={"q": TRAVEL_CONTEXT_QUERY, "maxResults": max_results},
            )
        except httpx.RequestError as exc:
            raise GmailAPIError(f"Gmail search failed ({type(exc).__name__}).") from None
        if listed.is_error:
            raise GmailAPIError(f"Gmail search failed (HTTP {listed.status_code}). Check authorization and Gmail API access.")
        try:
            message_ids = listed.json().get("messages") or []
        except (ValueError, AttributeError):
            raise GmailAPIError("Gmail returned an invalid message-list response.") from None

        items = []
        for message in message_ids[:max_results]:
            message_id = message.get("id") if isinstance(message, dict) else None
            if not message_id:
                continue
            try:
                detail = await client.get(
                    f"{GMAIL_API}/messages/{message_id}",
                    headers=headers,
                    params={
                        "format": "metadata",
                        "metadataHeaders": ["From", "Subject", "Date"],
                    },
                )
            except httpx.RequestError:
                continue
            if detail.is_error:
                continue
            try:
                payload = detail.json()
            except ValueError:
                continue
            headers_data = (payload.get("payload") or {}).get("headers") or []
            selected = {
                str(item.get("name", "")).casefold(): str(item.get("value", ""))
                for item in headers_data if isinstance(item, dict)
            }
            subject = selected.get("subject", "(No subject)")[:300]
            sender = selected.get("from", "")[:300]
            snippet = str(payload.get("snippet") or "")[:280]
            items.append({
                "message_id": message_id,
                "category": _category(subject, sender, snippet),
                "subject": subject,
                "from": sender,
                "received_at": selected.get("date", "")[:120],
                "snippet": snippet,
                "source": "Gmail",
            })

    return {
        "source": "Gmail",
        "permission": "read_only",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "query_window": "last 2 years",
        "count": len(items),
        "items": items,
        "content_persisted": False,
        "message_bodies_fetched": False,
    }
