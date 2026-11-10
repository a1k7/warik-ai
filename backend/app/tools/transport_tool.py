
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult


class TransportInput(BaseModel):
    origin: str = Field(..., description="Origin city")
    destination: str = Field(..., description="Destination city")
    date: str = Field(..., description="Travel date")


class TransportSearchTool(BaseTool):
    name = "search_indian_transport"

    description = (
        "Generate external train, bus, and flight search links "
        "for travel between two Indian cities. "
        "Does not check live availability or book tickets."
    )

    capability = "travel"
    input_schema = TransportInput
    requires_confirmation = False
    is_mutating = False

    provider_adapters = (
        {
            "provider_id": "irctc",
            "display_name": "IRCTC",
        },
        {
            "provider_id": "redbus",
            "display_name": "RedBus",
        },
        {
            "provider_id": "makemytrip",
            "display_name": "MakeMyTrip",
        },
    )

    supported_operations = ("link_generation",)

    @staticmethod
    def _provider_url(
        provider_id: str,
        params: TransportInput,
    ) -> tuple[str, str]:
        origin = params.origin
        destination = params.destination
        date = params.date

        if provider_id == "irctc":
            url = (
                "https://www.irctc.co.in/nget/train-search"
                f"?from={quote(origin)}"
                f"&to={quote(destination)}"
                f"&date={quote(date)}"
            )
            return "train", url

        if provider_id == "redbus":
            url = (
                "https://www.redbus.in/bus-tickets/"
                f"{quote(origin.lower())}-to-"
                f"{quote(destination.lower())}"
                f"?onward={quote(date)}"
            )
            return "bus", url

        if provider_id == "makemytrip":
            url = (
                "https://www.makemytrip.com/flights/domestic/"
                f"{quote(origin.lower())}-"
                f"{quote(destination.lower())}.html"
                f"?departureDate={quote(date)}"
            )
            return "flight", url

        raise ValueError(f"Unsupported transport provider: {provider_id}")

    def execute(
        self,
        ctx: ToolContext,
        params: TransportInput,
    ) -> ToolResult:
        links = {}

        for provider_id in ("irctc", "redbus", "makemytrip"):
            link_type, url = self._provider_url(provider_id, params)
            links[link_type] = url

        return ToolResult(
            success=True,
            message=(
                f"Here are external transport search links from "
                f"{params.origin} to {params.destination} "
                f"for {params.date}. These links do not represent "
                "confirmed availability or bookings."
            ),
            data={
                "type": "transport_links",
                "origin": params.origin,
                "destination": params.destination,
                "date": params.date,
                "links": links,
                "disclaimer": (
                    "These are external search links. "
                    "Live availability, prices, and ticket booking "
                    "must be checked on the provider website."
                ),
            },
        )

    def execute_for_provider(
        self,
        ctx: ToolContext,
        params: TransportInput,
        provider_id: str,
    ) -> ToolResult:
        provider_id = str(provider_id).lower()

        try:
            link_type, url = self._provider_url(provider_id, params)
        except ValueError as exc:
            return ToolResult(
                success=False,
                message=str(exc),
            )

        return ToolResult(
            success=True,
            message=(
                f"Generated a {provider_id} search link from "
                f"{params.origin} to {params.destination} "
                f"for {params.date}. This is not a confirmed booking."
            ),
            data={
                "type": "transport_links",
                "origin": params.origin,
                "destination": params.destination,
                "date": params.date,
                "provider_id": provider_id,
                "links": {
                    link_type: url,
                },
                "disclaimer": (
                    "This is an external search link. "
                    "Live availability, prices, and ticket booking "
                    "must be checked on the provider website."
                ),
            },
        )
