import subprocess
import json
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult

# ==========================================
# 1. FLIGHT SEARCH TOOL
# ==========================================
class FlightInput(BaseModel):
    origin: str = Field(..., description="IATA code of the origin city (e.g., BOM)")
    destination: str = Field(..., description="IATA code of the destination city (e.g., DEL)")
    date: str = Field(..., description="Departure date in YYYY-MM-DD format")

class TrvlFlightSearchTool(BaseTool):
    name = "search_flights_trvl"
    description = "Find real-time flight prices and schedules using the free trvl service."
    input_schema = FlightInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: FlightInput) -> ToolResult:
        try:
            # FIXED: Correct positional arguments for flights
            result = subprocess.run(
                ["trvl", "flights", params.origin.upper(), params.destination.upper(), params.date, "--format", "json"],
                capture_output=True, text=True, check=True
            )
            
            data = json.loads(result.stdout)
            flights = data.get("results", [])
            
            if not flights:
                return ToolResult(success=True, message=f"No flights found from {params.origin} to {params.destination} on {params.date}.")

            message = f"Found {len(flights)} real flights from {params.origin.upper()} to {params.destination.upper()}:\n\n"
            
            for f in flights[:5]: # Limit to top 5
                price = f.get("price", 0)
                currency = f.get("currency", "INR")
                price_str = f"₹{price}" if price and price > 0 else "Check link for price"
                
                legs = f.get("legs", [])
                if legs:
                    first_leg = legs[0]
                    last_leg = legs[-1]
                    airline = first_leg.get("airline", "Unknown")
                    dep_time = first_leg.get("departure_time", "").replace("T", " ")
                    arr_time = last_leg.get("arrival_time", "").replace("T", " ")
                    stops = f.get("stops", 0)
                    stops_str = "Direct" if stops == 0 else f"{stops} Stop(s)"
                    
                    message += f"- **{airline}** ({stops_str}): Departs {dep_time} → Arrives {arr_time} | Price: {price_str}\n"
                    message += f"  Book: {f.get('booking_url')}\n\n"

            return ToolResult(success=True, message=message, data={"flights": flights[:5]})
            
        except subprocess.CalledProcessError as e:
            return ToolResult(success=False, message=f"trvl command failed: {e.stderr}")
        except Exception as e:
            return ToolResult(success=False, message=f"Error using trvl: {str(e)}")


# ==========================================
# 2. HOTEL SEARCH TOOL
# ==========================================
class HotelInput(BaseModel):
    city: str = Field(..., description="City name (e.g., Indore)")
    check_in: str = Field(..., description="YYYY-MM-DD")
    check_out: str = Field(..., description="YYYY-MM-DD")

class TrvlHotelSearchTool(BaseTool):
    name = "search_hotels_trvl"
    description = "Find real-time hotel prices using the free trvl service."
    input_schema = HotelInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: HotelInput) -> ToolResult:
        try:
            # FIXED: --checkin and --checkout (no hyphens)
            result = subprocess.run(
                ["trvl", "hotels", params.city, "--checkin", params.check_in, "--checkout", params.check_out, "--format", "json"],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            hotels = data.get("results", [])
            
            if not hotels:
                return ToolResult(success=True, message=f"No hotels found in {params.city}.")

            message = f"Found real hotels in {params.city}:\n\n"
            for h in hotels[:5]:
                name = h.get("name", "Unknown Hotel")
                price = h.get("price", 0)
                currency = h.get("currency", "INR")
                rating = h.get("rating", "N/A")
                price_str = f"₹{price}" if price and price > 0 else "Check link"
                booking_url = h.get("booking_url", "")
                
                message += f"- **{name}** (Rating: {rating}) | Total: {price_str}\n"
                if booking_url:
                    message += f"  Book: {booking_url}\n"
                message += "\n"

            return ToolResult(success=True, message=message, data={"hotels": hotels[:5]})
        except subprocess.CalledProcessError as e:
            return ToolResult(success=False, message=f"trvl command failed: {e.stderr}")
        except Exception as e:
            return ToolResult(success=False, message=f"Error using trvl: {str(e)}")