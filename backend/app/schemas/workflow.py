
from datetime import datetime
from typing import Literal, Optional, Any
from app.tools.provider_selector import ProviderSelector
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
StepStatus = Literal[
    "PENDING",
    "READY",
    "AWAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "EXECUTING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
    "CANCELLED",
    "RECONCILIATION_REQUIRED",
]


class WorkflowInputBinding(BaseModel):
    """A declarative reference to data produced by a direct workflow dependency."""

    model_config = ConfigDict(extra="forbid")

    source_step: str = Field(min_length=1, max_length=100)
    source_path: str = Field(
        min_length=1,
        max_length=512,
        pattern=r"^[A-Za-z0-9_-]+(?:\.(?:[A-Za-z0-9_-]+|[0-9]+))*$",
        description="Dot path through JSON objects and arrays, e.g. items.0.address",
    )
    required: bool = True
    requires_verified: bool = False

    @field_validator("source_path")
    @classmethod
    def reject_dunder_path_segments(cls, value: str) -> str:
        if any(segment.startswith("__") for segment in value.split(".")):
            raise ValueError("dunder/object-introspection paths are not allowed")
        return value


class WorkflowStep(BaseModel):
    id: str
    description: str
    tool: str
    params: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    input_bindings: dict[str, WorkflowInputBinding] = Field(
        default_factory=dict
    )

    provider_id: Optional[str] = None
    provider_operation: Optional[str] = None
    provider_region: Optional[str] = None

    approval_required: bool = False
    required: bool = True
    dep_policy: Literal["all_success", "tolerate_failure"] = "all_success"
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_count: int = Field(default=0, ge=0)
    status: StepStatus = "PENDING"
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

class WorkflowPlan(BaseModel):
    goal_title: str = "User goal"
    goal_description: str = ""
    context: dict = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(default_factory=list)

    # Backward compatibility with existing tests and callers
    goal: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_goal(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            if not values.get("goal_title") and values.get("goal"):
                values["goal_title"] = values["goal"]
        return values


class WorkflowResponse(BaseModel):
    id: int
    goal_id: int
    status: str
    steps: list[dict] = Field(default_factory=list)
    created_at: datetime
