
"""Base classes for all Warik AI tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import User


@dataclass
class ToolContext:
    db: Session
    user: User


@dataclass
class ToolResult:
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    retry_safe: bool = False


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    capability: str = "general"

    input_schema: Type[BaseModel]

    requires_confirmation: bool = False
    is_mutating: bool = False

    execution_status: str = "available"

    provider_adapters: tuple[dict[str, Any], ...] = ()
    supported_operations: tuple[str, ...] = ("execute",)
    supported_regions: tuple[str, ...] = ()
    requires_auth: bool = False

    def confirmation_prompt(self, params: BaseModel) -> str:
        return f"run {self.name}"

    def verify(
        self,
        ctx: ToolContext,
        params: BaseModel,
        result: ToolResult,
    ) -> Optional[dict[str, Any]]:
        """Independently verify a successful side effect when supported."""
        return None

    def execute_for_provider(
        self,
        ctx: ToolContext,
        params: BaseModel,
        provider_id: str,
    ) -> ToolResult:
        """Execute using one declared provider adapter.

        Single-provider tools can use their existing execute() implementation.
        Multi-provider tools must explicitly implement provider-specific behavior.
        """
        adapters = {
            str(adapter.get("provider_id", "")).lower()
            for adapter in self.provider_adapters
        }
        requested = str(provider_id).lower()

        if requested not in adapters:
            return ToolResult(
                success=False,
                message=(
                    f"Provider '{provider_id}' is not registered "
                    f"for tool '{self.name}'."
                ),
            )

        if len(adapters) > 1:
            return ToolResult(
                success=False,
                message=(
                    f"Tool '{self.name}' does not implement "
                    "provider-specific execution."
                ),
            )

        return self.execute(ctx, params)

    @abstractmethod
    def execute(
        self,
        ctx: ToolContext,
        params: BaseModel,
    ) -> ToolResult:
        ...
