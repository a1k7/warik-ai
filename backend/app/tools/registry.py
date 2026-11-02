"""Central tool registry and dispatcher with audit logging."""

from typing import Optional
from pydantic import ValidationError

from app.models import ActionLog
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.tools.expenses import AddExpenseTool, CalculateExpenseSummaryTool, ListExpensesTool
from app.tools.memory import DeleteMemoryTool, RetrieveMemoryTool, SaveMemoryTool
from app.tools.reminders import CreateReminderTool, ListRemindersTool
from app.tools.tasks import CompleteTaskTool, CreateTaskTool, ListTasksTool
from app.tools.travel import CreateTravelPlanTool

# Import the NEW Premium Travel Tools
from app.tools.travel_apis import (
    GeoapifyPlacesTool,
    RealFlightSearchTool,
    StayApiHotelTool,
    CabDeepLinkTool
)

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in [
            # Task & Expense Tools
            CreateTaskTool(),
            ListTasksTool(),
            CompleteTaskTool(),
            CreateReminderTool(),
            ListRemindersTool(),
            AddExpenseTool(),
            ListExpensesTool(),
            CalculateExpenseSummaryTool(),
            CreateTravelPlanTool(),
            SaveMemoryTool(),
            RetrieveMemoryTool(),
            DeleteMemoryTool(),
            
            # NEW Premium Travel Tools
            GeoapifyPlacesTool(),
            RealFlightSearchTool(),
            StayApiHotelTool(),
            CabDeepLinkTool(),
        ]:
            self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def dispatch(self, ctx: ToolContext, name: str, raw_params: dict) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(success=False, message=f"Unknown tool: {name}")

        try:
            params = tool.input_schema(**raw_params)
        except ValidationError as exc:
            first = exc.errors()[0]
            field = first["loc"][0] if first["loc"] else "argument"
            return ToolResult(success=False, message=f"Invalid argument '{field}': {first['msg']}")

        try:
            result = tool.execute(ctx, params)
        except Exception as exc:
            ctx.db.rollback()
            self._log(ctx, name, raw_params, "failed", str(exc))
            return ToolResult(success=False, message=f"Tool '{name}' failed: {exc}")

        self._log(ctx, name, raw_params, "success" if result.success else "failed", result.message)
        return result

    def _log(self, ctx: ToolContext, tool_name: str, payload: dict, status: str, message: str) -> None:
        try:
            ctx.db.add(ActionLog(
                user_id=ctx.user.id,
                action=f"tool.{tool_name}",
                tool_name=tool_name,
                payload=payload,
                result_status=status,
                result_message=(message or "")[:1000] or None,
            ))
            ctx.db.commit()
        except Exception:
            ctx.db.rollback()

registry = ToolRegistry()