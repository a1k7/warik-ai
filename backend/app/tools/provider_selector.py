

"""Capability-aware provider selection and deterministic fallback."""

from dataclasses import dataclass
from typing import Any, Iterable, Optional


ELIGIBLE_STATUSES = {"available", "partially_available"}
STATUS_PRIORITY = {
    "available": 0,
    "partially_available": 1,
}


@dataclass(frozen=True)
class ProviderCandidate:
    tool_name: str
    provider_id: str
    display_name: str
    capability: str
    operations: tuple[str, ...]
    regions: tuple[str, ...]
    requires_auth: bool
    execution_status: str
    priority: int


@dataclass(frozen=True)
class RejectedProvider:
    tool_name: str
    provider_id: str
    reason: str


@dataclass(frozen=True)
class ProviderSelection:
    capability: str
    operation: str
    region: Optional[str]
    selected: Optional[ProviderCandidate]
    candidates: tuple[ProviderCandidate, ...]
    rejected: tuple[RejectedProvider, ...]

    @property
    def available(self) -> bool:
        return self.selected is not None

    def next_candidate(
        self,
        failed_provider_ids: Iterable[str] = (),
    ) -> Optional[ProviderCandidate]:
        """Return the next provider for the same tool contract."""
        if self.selected is None:
            return None

        failed = {item.lower() for item in failed_provider_ids}

        for candidate in self.candidates:
            if candidate.tool_name != self.selected.tool_name:
                continue
            if candidate.provider_id.lower() not in failed:
                return candidate

        return None


class ProviderSelector:
    """Select registered provider adapters for a capability and operation.

    This class evaluates metadata only. It does not execute tools, make
    reservations, place orders, or perform payments.
    """

    def __init__(
        self,
        registry: Any,
        provider_priority: Optional[dict[str, int]] = None,
    ) -> None:
        self.registry = registry
        self.provider_priority = {
            key.strip().lower(): value
            for key, value in (provider_priority or {}).items()
        }

    @staticmethod
    def _normalize(value: Optional[str]) -> str:
        return (value or "").strip().lower()

    def _priority(self, provider_id: str) -> int:
        return self.provider_priority.get(provider_id.lower(), 100)

    def select(
        self,
        capability: str,
        operation: str,
        region: Optional[str] = None,
        authenticated_providers: Iterable[str] = (),
        exclude_provider_ids: Iterable[str] = (),
        tool_name: Optional[str] = None,
    ) -> ProviderSelection:
        """Return the best eligible provider and same-tool fallback candidates.

        If a region is requested, the provider must explicitly declare it.
        An empty region list means unknown coverage, not global coverage.

        Pass tool_name when a capability contains multiple distinct tool
        contracts, such as flight search and hotel search under travel.
        """

        requested_capability = self._normalize(capability)
        requested_operation = self._normalize(operation)
        requested_region = self._normalize(region)
        requested_tool = self._normalize(tool_name)

        authenticated = {
            self._normalize(item) for item in authenticated_providers
        }
        excluded = {
            self._normalize(item) for item in exclude_provider_ids
        }

        candidates: list[ProviderCandidate] = []
        rejected: list[RejectedProvider] = []

        for registered_name in self.registry.list_tools():
            tool = self.registry.get(registered_name)
            if tool is None:
                continue

            actual_tool_name = self._normalize(
                getattr(tool, "name", registered_name)
            )

            if requested_tool and actual_tool_name != requested_tool:
                continue

            tool_capability = self._normalize(
                getattr(tool, "capability", "general")
            )
            if tool_capability != requested_capability:
                continue

            adapters = getattr(tool, "provider_adapters", ()) or ()
            operations = tuple(
                self._normalize(item)
                for item in (
                    getattr(tool, "supported_operations", ("execute",))
                    or ()
                )
            )
            regions = tuple(
                self._normalize(item)
                for item in (
                    getattr(tool, "supported_regions", ()) or ()
                )
            )

            for adapter in adapters:
                provider_id = self._normalize(
                    adapter.get("provider_id")
                )
                if not provider_id:
                    continue

                display_name = str(
                    adapter.get("display_name") or provider_id
                )

                def reject(reason: str) -> None:
                    rejected.append(
                        RejectedProvider(
                            tool_name=actual_tool_name,
                            provider_id=provider_id,
                            reason=reason,
                        )
                    )

                if provider_id in excluded:
                    reject("Provider was explicitly excluded.")
                    continue

                if requested_operation not in operations:
                    reject(
                        f"Operation '{requested_operation}' is not supported."
                    )
                    continue

                if requested_region:
                    if not regions:
                        reject(
                            "Provider has no declared regional coverage."
                        )
                        continue

                    if requested_region not in regions:
                        reject(
                            f"Provider does not declare coverage for "
                            f"'{requested_region}'."
                        )
                        continue

                status = self._normalize(
                    getattr(tool, "execution_status", "available")
                )

                if (
                    status not in ELIGIBLE_STATUSES
                    and status != "requires_auth"
                ):
                    reject(
                        f"Execution status '{status}' is not eligible."
                    )
                    continue

                requires_auth = bool(
                    getattr(tool, "requires_auth", False)
                ) or status == "requires_auth"

                if requires_auth and provider_id not in authenticated:
                    reject("Provider authentication is required.")
                    continue

                candidates.append(
                    ProviderCandidate(
                        tool_name=actual_tool_name,
                        provider_id=provider_id,
                        display_name=display_name,
                        capability=tool_capability,
                        operations=operations,
                        regions=regions,
                        requires_auth=requires_auth,
                        execution_status=status,
                        priority=self._priority(provider_id),
                    )
                )

        candidates.sort(
            key=lambda item: (
                item.priority,
                STATUS_PRIORITY.get(item.execution_status, 99),
                item.provider_id,
                item.tool_name,
            )
        )

        selected = candidates[0] if candidates else None

        return ProviderSelection(
            capability=requested_capability,
            operation=requested_operation,
            region=region,
            selected=selected,
            candidates=tuple(candidates),
            rejected=tuple(rejected),
        )
