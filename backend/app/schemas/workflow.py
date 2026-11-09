
from datetime import datetime
from typing import Literal, Optional, Any

from pydantic import BaseModel, Field

from pydantic import BaseModel, Field, model_validator
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
]


class WorkflowStep(BaseModel):
    id: str
    description: str
    tool: str
    params: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    approval_required: bool = False

    # Workflow execution policies
    required: bool = True
    dep_policy: Literal["all_success", "tolerate_failure"] = "all_success"
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_count: int = Field(default=0, ge=0)

    # Execution state
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
