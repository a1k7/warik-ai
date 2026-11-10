
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

from app.tools.transport_tool import TransportSearchTool

# Other tools
from app.tools.web_search import WebSearchTool
from app.tools.web_research import WebResearchTool
from app.tools.financial_tools import SavingsPlanTool
from app.tools.trip_summary_tool import CompileTripSummaryTool
from app.tools.document_tool import AnswerDocumentTool


class ToolRegistry:
    """Central registry for Warik AI's executable tools.

    The registry remains the single source of truth for:
    - Tool lookup
    - Tool execution
    - Capability discovery
    - Provider metadata discovery
    """

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
            TransportSearchTool(),
            GenerateAdvancedItineraryTool(),
            SaveTripTool(),
            CalculateBudgetTool(),
            OptimizeRouteTool(),
            GenerateItineraryTool(),
            CompileTripSummaryTool(),

            # Other
            WebSearchTool(),
            WebResearchTool(),
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
        """Return a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Return all registered tool names."""
        return sorted(self._tools.keys())

    def describe_tools(self) -> list[dict]:
        """Return the live capability manifest used by the planner."""

        manifest = []

        for name in sorted(self._tools):
            tool = self._tools[name]

            manifest.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "capability": getattr(
                        tool, "capability", "general"
                    ),
                    "input_schema": tool.input_schema.model_json_schema(),
                    "requires_confirmation": bool(
                        getattr(tool, "requires_confirmation", False)
                    ),
                    "is_mutating": bool(
                        getattr(tool, "is_mutating", False)
                    ),
                    "execution_status": getattr(
                        tool, "execution_status", "available"
                    ),
                    "provider_adapters": [
                        {
                            "provider_id": adapter["provider_id"],
                            "display_name": adapter["display_name"],
                        }
                        for adapter in getattr(
                            tool, "provider_adapters", ()
                        )
                    ],
                    "supported_operations": list(
                        getattr(
                            tool,
                            "supported_operations",
                            ("execute",),
                        )
                    ),
                    "supported_regions": list(
                        getattr(tool, "supported_regions", ())
                    ),
                    "requires_auth": bool(
                        getattr(tool, "requires_auth", False)
                    ),
                }
            )

        return manifest

    def describe_providers(self) -> list[dict]:
        """Return provider adapters exposed by registered tools.

        Metadata describes declared integration capabilities. It does not
        prove provider reachability, live availability, or transaction success.
        """

        providers = []

        for name in sorted(self._tools):
            tool = self._tools[name]

            for adapter in getattr(tool, "provider_adapters", ()):
                providers.append(
                    {
                        "provider_id": adapter["provider_id"],
                        "display_name": adapter["display_name"],
                        "tool_name": tool.name,
                        "capability": getattr(
                            tool, "capability", "general"
                        ),
                        "operations": list(
                            getattr(
                                tool,
                                "supported_operations",
                                ("execute",),
                            )
                        ),
                        "regions": list(
                            getattr(tool, "supported_regions", ())
                        ),
                        "requires_auth": bool(
                            getattr(tool, "requires_auth", False)
                        ),
                        "execution_status": getattr(
                            tool, "execution_status", "available"
                        ),
                    }
                )

        return providers

    def find_tools(
        self,
        capability: Optional[str] = None,
        operation: Optional[str] = None,
        region: Optional[str] = None,
        include_unavailable: bool = False,
    ) -> list[BaseTool]:
        """Find tools matching declared capability metadata.

        Geographic coverage is never assumed. If a region is requested,
        the tool must explicitly declare that region.
        """

        matches = []

        for name in sorted(self._tools):
            tool = self._tools[name]

            tool_capability = getattr(
                tool, "capability", "general"
            )

            if capability and tool_capability != capability:
                continue

            operations = getattr(
                tool, "supported_operations", ("execute",)
            )

            if operation and operation not in operations:
                continue

            if region:
                regions = getattr(tool, "supported_regions", ())

                declared_regions = {
                    item.lower() for item in regions
                }

                if region.lower() not in declared_regions:
                    continue

            status = getattr(
                tool, "execution_status", "available"
            )

            if (
                not include_unavailable
                and status == "unavailable"
            ):
                continue

            matches.append(tool)

        return matches


    def dispatch(
        self,
        ctx: ToolContext,
        name: str,
        raw_params: dict,
        provider_id: Optional[str] = None,
    ) -> ToolResult:
        """Validate and execute a registered tool, optionally via one provider."""

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
            if provider_id is None:
                result = tool.execute(ctx, params)
            else:
                result = tool.execute_for_provider(
                    ctx,
                    params,
                    provider_id,
                )
        except Exception as exc:
            ctx.db.rollback()
            return ToolResult(
                success=False,
                message=f"Tool '{name}' failed: {str(exc)}",
            )

        if result.success:
            payload = raw_params
            if provider_id is not None:
                payload = {
                    "params": raw_params,
                    "provider_id": provider_id,
                }

            try:
                ctx.db.add(
                    ActionLog(
                        user_id=ctx.user.id,
                        action=f"tool.{name}",
                        tool_name=name,
                        payload=payload,
                        result_status="success",
                        result_message=result.message[:1000],
                    )
                )
                ctx.db.commit()
            except Exception:
                ctx.db.rollback()

        return result



# Global registry instance used by the application.
registry = ToolRegistry()
