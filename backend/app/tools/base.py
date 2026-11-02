"""Base classes for all Warik AI tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Type

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
    input_schema: Type[BaseModel]
    requires_confirmation: bool = False

    def confirmation_prompt(self, params: BaseModel) -> str:
        return f"run {self.name}"

    @abstractmethod
    def execute(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        ...