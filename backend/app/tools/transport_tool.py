from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from urllib.parse import quote

class TransportInput(BaseModel):
    origin: str = Field(...)
    destination: str = Field(...)
    date: str = Field(...)

class TransportSearchTool(BaseTool):
    name = "search_indian_transport"
    description = "Find trains, buses, and flights between two Indian cities. Generates IRCTC and RedBus deep links."
    capability = "travel"
    input_schema = TransportInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: TransportInput) -> ToolResult:
        try:
            # 1. Generate IRCTC Train Link
            train_link = f"https://www.irctc.co.in/nget/train-search?from={quote(params.origin)}&to={quote(params.destination)}&date={params.date}"

            # 2. Generate RedBus Link
            bus_link = f"https://www.redbus.in/bus-tickets/{quote(params.origin.lower())}-to-{quote(params.destination.lower())}?onward={params.date}"

            # 3. Generate Flight Link (MakeMyTrip)
            flight_link = f"https://www.makemytrip.com/flights/domestic/{quote(params.origin.lower())}-{quote(params.destination.lower())}.html?departureDate={params.date}"

            data = {
                "type": "transport_links",
                "origin": params.origin,
                "destination": params.destination,
                "date": params.date,
                "links": {
                    "train": train_link,
                    "bus": bus_link,
                    "flight": flight_link
                }
            }

            return ToolResult(
                success=True,
                message=f"Here are the transport options from {params.origin} to {params.destination} on {params.date}.",
                data=data
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Transport search failed: {str(e)}")
