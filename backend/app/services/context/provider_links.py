"""Provider-link validation for travel search and handoff URLs.

This is intentionally an allowlist/URL-structure check only. It never claims a
URL is reachable, bookable, inventory-backed, or a confirmed booking.
"""
from __future__ import annotations

from copy import deepcopy
import ipaddress
from typing import Any
from urllib.parse import urlsplit

_ALLOWED_HOSTS = {
    "flights": (
        "google.com", "makemytrip.com", "goibibo.com", "cleartrip.com",
        "ixigo.com", "skyscanner.co.in", "expedia.com", "kayak.com",
        "goindigo.in", "spicejet.com", "airindia.com", "akasaair.com",
        "airindiaexpress.com",
    ),
    "hotels": (
        "booking.com", "agoda.com", "expedia.com", "hotels.com",
        "makemytrip.com", "goibibo.com", "cleartrip.com", "airbnb.com",
        "trivago.com",
    ),
    "transfers": ("uber.com", "olacabs.com"),
}
_PROVIDER_HOSTS = {
    "uber": ("uber.com",),
    "ola": ("olacabs.com",),
}
_TRAVEL_TOOL_ARTIFACT = {
    "search_flights_real": "flights",
    "search_hotels_stayapi": "hotels",
    "get_cab_links": "transfers",
}
_URL_FIELDS = ("url", "booking_url", "handoff_url", "deep_link")


def _host_matches(host: str, roots: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == root or host.endswith("." + root) for root in roots)


def validate_provider_url(
    value: Any,
    *,
    artifact: str,
    provider_id: str | None = None,
) -> dict[str, Any]:
    """Validate HTTPS, host allowlisting and optional provider-host binding.

    `allowlisted_format_unverified` means only the URL structure and domain
    allowlist passed. No network request or landing-page verification occurred.
    """
    raw = value if isinstance(value, str) else ""
    result: dict[str, Any] = {
        "status": "rejected",
        "link_kind": "external_handoff",
        "host": None,
        "network_checked": False,
        "reachable": None,
        "reason": None,
    }
    if not raw or len(raw) > 4096 or any(ch.isspace() for ch in raw):
        result["reason"] = "URL is empty, too long, or contains whitespace."
        return result
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        if parsed.scheme.lower() != "https":
            result["reason"] = "Only HTTPS links are allowed."
            return result
        if not host or parsed.username or parsed.password:
            result["reason"] = "URL has no valid host or contains embedded credentials."
            return result
        if port not in (None, 443):
            result["reason"] = "Non-standard URL ports are not allowed."
            return result
        try:
            ipaddress.ip_address(host.strip("[]"))
            result["reason"] = "IP-literal hosts are not allowed for provider handoffs."
            return result
        except ValueError:
            pass
    except (TypeError, ValueError):
        result["reason"] = "URL could not be parsed safely."
        return result

    roots = _ALLOWED_HOSTS.get(artifact, ())
    if not _host_matches(host, roots):
        result.update(host=host, reason=f"Host is not allowlisted for {artifact} handoffs.")
        return result

    if provider_id:
        expected = _PROVIDER_HOSTS.get(provider_id.lower())
        if expected and not _host_matches(host, expected):
            result.update(host=host, reason=f"Host does not match the declared {provider_id} provider.")
            return result

    result.update(
        status="allowlisted_format_unverified",
        host=host,
        link_kind=("search_handoff" if artifact in {"flights", "hotels"} else "ride_handoff"),
        reason="HTTPS URL and provider-domain allowlist passed; destination reachability was not checked.",
    )
    return result


def _validate_field(item: dict[str, Any], field: str, artifact: str, provider_id: str | None = None) -> dict[str, Any] | None:
    value = item.get(field)
    if value in (None, ""):
        return None
    validation = validate_provider_url(value, artifact=artifact, provider_id=provider_id)
    item[f"{field}_validation"] = validation
    if validation["status"] != "allowlisted_format_unverified":
        item[field] = None
        item[f"{field}_rejected_reason"] = validation.get("reason")
    else:
        item[f"{field}_kind"] = validation["link_kind"]
    return validation


def sanitize_travel_payload(tool_name: str, payload: dict[str, Any], provider_id: str | None = None) -> dict[str, Any]:
    """Copy and sanitize URL-bearing fields from registered travel tools."""
    artifact = _TRAVEL_TOOL_ARTIFACT.get(str(tool_name or ""))
    if artifact is None or not isinstance(payload, dict):
        return payload

    data = deepcopy(payload)
    validation_summary: list[dict[str, Any]] = []

    if data.get("search_url"):
        search_validation = validate_provider_url(
            data.get("search_url"), artifact=artifact,
            provider_id=provider_id if artifact == "transfers" else None,
        )
        data["search_url_validation"] = search_validation
        if search_validation["status"] != "allowlisted_format_unverified":
            data["search_url"] = None
        else:
            search_validation["link_kind"] = "search_handoff"
        validation_summary.append({"field": "search_url", **search_validation})

    items = data.get("items")
    if isinstance(items, list):
        sanitized_items = []
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            item = deepcopy(raw_item)
            for field in _URL_FIELDS:
                checked = _validate_field(item, field, artifact)
                if checked:
                    validation_summary.append({"field": field, **checked})
            nested = item.get("links")
            if isinstance(nested, dict):
                clean_links = {}
                nested_validation = {}
                for key, url in nested.items():
                    checked = validate_provider_url(
                        url, artifact=artifact,
                        provider_id=str(key).lower() if artifact == "transfers" else None,
                    )
                    nested_validation[str(key)] = checked
                    validation_summary.append({"field": f"items.links.{key}", **checked})
                    if checked["status"] == "allowlisted_format_unverified":
                        clean_links[key] = url
                item["links"] = clean_links
                item["links_validation"] = nested_validation
            sanitized_items.append(item)
        data["items"] = sanitized_items

    links = data.get("links")
    if isinstance(links, dict):
        clean_links = {}
        link_validation = {}
        for key, url in links.items():
            checked = validate_provider_url(
                url, artifact=artifact,
                provider_id=str(key).lower() if artifact == "transfers" else None,
            )
            link_validation[str(key)] = checked
            validation_summary.append({"field": f"links.{key}", **checked})
            if checked["status"] == "allowlisted_format_unverified":
                clean_links[key] = url
        data["links"] = clean_links
        data["links_validation"] = link_validation

    data["link_validation_summary"] = {
        "method": "https_scheme_and_provider_host_allowlist",
        "network_checked": False,
        "reachable": None,
        "booking_completed": False,
        "disclaimer": "Allowlisted format does not prove the destination page is reachable, has live availability, or completes a booking.",
        "checked_links": len(validation_summary),
        "rejected_links": sum(1 for item in validation_summary if item.get("status") == "rejected"),
    }
    return data
