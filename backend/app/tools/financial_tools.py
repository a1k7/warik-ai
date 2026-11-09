from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.agents.budget_calculator import calculate_savings_plan, format_savings_plan_markdown

class SavingsPlanInput(BaseModel):
    monthly_income: float = Field(..., gt=0)
    rent: float = Field(default=0, ge=0)
    food: float = Field(default=0, ge=0)
    travel: float = Field(default=0, ge=0)

class SavingsPlanTool(BaseTool):
    name = "calculate_savings_plan"
    description = "Deterministically calculate a monthly savings plan."
    capability = "financial"
    input_schema = SavingsPlanInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: SavingsPlanInput) -> ToolResult:
        try:
            plan = calculate_savings_plan(params.monthly_income, params.rent, params.food, params.travel)
            markdown = format_savings_plan_markdown(plan)
            return ToolResult(success=True, message=markdown, data={"type": "savings_plan", "plan": plan.__dict__})
        except Exception as e:
            return ToolResult(success=False, message=f"Budget calculation failed: {str(e)}")