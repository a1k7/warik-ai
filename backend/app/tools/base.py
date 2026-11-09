"""Base classes for all Warik AI tools."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Type, Optional
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

class BaseTool(ABC):
    name: str = ""
    description: str = ""
    capability: str = "general" # e.g., "research", "travel", "food", "action"
    input_schema: Type[BaseModel]
    requires_confirmation: bool = False
    is_mutating: bool = False # True if it changes external state (booking, ordering)
    execution_status: str = "available" # available, partially_available, requires_auth, unavailable

    def confirmation_prompt(self, params: BaseModel) -> str:
        return f"run {self.name}"

    @abstractmethod
    def execute(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        ...