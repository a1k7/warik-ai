
from typing import Optional

from pydantic import ValidationError

from app.models import ActionLog
from app.tools.base import BaseTool, ToolContext, ToolResult

# Productivity tools
from app.tools.tasks import (
    CreateTaskTool,
    ListTasksTool,
    CompleteTaskTool,
)
from app.tools.expenses import (
    AddExpenseTool,
    ListExpensesTool,
    CalculateExpenseSummaryTool,
)
from app.tools.reminders import (
    CreateReminderTool,
    ListRemindersTool,
)

# Food tools
from app.tools.food_tools import (
    DiscoverFoodTool,
    SaveFavoriteRestaurantTool,
)

from app.tools.food_order_tool import ZomatoSearchTool

# Travel tools
from app.tools.trip_tools import (
    GenerateAdvancedItineraryTool,
    SaveTripTool,
)
from app.tools.trip_planner import (
    CalculateBudgetTool,
    OptimizeRouteTool,
    GenerateItineraryTool,
)
from app.tools.travel_apis import (
    RealFlightSearchTool,
    StayApiHotelTool,
    GeoapifyPlacesTool,
    CabDeepLinkTool,
)

# Other tools
from app.tools.web_search import WebSearchTool
from app.tools.financial_tools import SavingsPlanTool
from app.tools.trip_summary_tool import CompileTripSummaryTool
from app.tools.document_tool import AnswerDocumentTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

        tools = [
            # Productivity
            CreateTaskTool(),
            ListTasksTool(),
            CompleteTaskTool(),
            AddExpenseTool(),
            ListExpensesTool(),
            CalculateExpenseSummaryTool(),
            CreateReminderTool(),
            ListRemindersTool(),

            # Food
            DiscoverFoodTool(),
            SaveFavoriteRestaurantTool(),
            ZomatoSearchTool(),

            # Travel
            RealFlightSearchTool(),
            StayApiHotelTool(),
            GeoapifyPlacesTool(),
            CabDeepLinkTool(),
            GenerateAdvancedItineraryTool(),
            SaveTripTool(),
            CalculateBudgetTool(),
            OptimizeRouteTool(),
            GenerateItineraryTool(),
            CompileTripSummaryTool(),

            # Other
            WebSearchTool(),
            SavingsPlanTool(),
            AnswerDocumentTool(),
        ]

        for tool in tools:
            if not tool.name:
                raise ValueError(
                    f"Tool {tool.__class__.__name__} has no registered name."
                )

            if tool.name in self._tools:
                raise ValueError(
                    f"Duplicate tool registration: {tool.name}"
                )

            self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def describe_tools(self) -> list[dict]:
        """Return a machine-readable capability manifest for planners and UI."""
        manifest = []
        for name in sorted(self._tools):
            tool = self._tools[name]
            schema = tool.input_schema.model_json_schema()
            manifest.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "capability": getattr(tool, "capability", "general"),
                    "input_schema": schema,
                    "requires_confirmation": bool(
                        getattr(tool, "requires_confirmation", False)
                    ),
                    "is_mutating": bool(getattr(tool, "is_mutating", False)),
                    "execution_status": getattr(
                        tool, "execution_status", "available"
                    ),
                }
            )
        return manifest

    def dispatch(
        self,
        ctx: ToolContext,
        name: str,
        raw_params: dict,
    ) -> ToolResult:

        tool = self.get(name)

        if tool is None:
            return ToolResult(
                success=False,
                message=f"Unknown tool: {name}",
            )

        try:
            params = tool.input_schema(**raw_params)

        except ValidationError as exc:
            first_error = exc.errors()[0]

            return ToolResult(
                success=False,
                message=f"Invalid arguments: {first_error['msg']}",
            )

        try:
            result = tool.execute(ctx, params)

        except Exception as exc:
            ctx.db.rollback()

            return ToolResult(
                success=False,
                message=f"Tool '{name}' failed: {str(exc)}",
            )

        # Record successful tool executions.
        if result.success:
            try:
                ctx.db.add(
                    ActionLog(
                        user_id=ctx.user.id,
                        action=f"tool.{name}",
                        tool_name=name,
                        payload=raw_params,
                        result_status="success",
                        result_message=result.message[:1000],
                    )
                )
                ctx.db.commit()

            except Exception:
                ctx.db.rollback()

        return result


registry = ToolRegistry()
