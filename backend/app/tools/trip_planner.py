import math
from typing import List, Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.models import TravelPlan, TravelStop

class BudgetInput(BaseModel):
    flights_cost: float = Field(default=0)
    hotel_cost_per_night: float = Field(default=0)
    nights: int = Field(default=1)
    food_cost_per_day: float = Field(default=1000)
    days: int = Field(default=1)
    activities_cost: float = Field(default=0)
    total_budget: float = Field(...)

class CalculateBudgetTool(BaseTool):
    name = "calculate_trip_budget"
    description = "Calculate total trip cost and check if it fits the budget."
    input_schema = BudgetInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: BudgetInput) -> ToolResult:
        hotel_total = params.hotel_cost_per_night * params.nights
        food_total = params.food_cost_per_day * params.days
        total = params.flights_cost + hotel_total + food_total + params.activities_cost
        remaining = params.total_budget - total

        status = "Under Budget! 🎉" if remaining >= 0 else "Over Budget! ⚠️"

        message = f"**Trip Budget Summary**\n"
        message += f"- Flights: ₹{params.flights_cost:,.0f}\n"
        message += f"- Hotel ({params.nights} nights): ₹{hotel_total:,.0f}\n"
        message += f"- Food ({params.days} days): ₹{food_total:,.0f}\n"
        message += f"- Activities: ₹{params.activities_cost:,.0f}\n"
        message += f"---\n"
        message += f"**Total Estimated Cost: ₹{total:,.0f}**\n"
        message += f"**Status: {status} (Remaining: ₹{remaining:,.0f})**"

        return ToolResult(success=True, message=message)

class PlaceItem(BaseModel):
    name: str
    lat: float
    lon: float

class RouteInput(BaseModel):
    places: List[PlaceItem]

class OptimizeRouteTool(BaseTool):
    name = "optimize_route"
    description = "Sort a list of places into the most efficient route."
    input_schema = RouteInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: RouteInput) -> ToolResult:
        if len(params.places) < 2:
            return ToolResult(success=True, message="Need at least 2 places to optimize a route.")

        def haversine(p1: PlaceItem, p2: PlaceItem) -> float:
            R = 6371.0
            lat1, lon1, lat2, lon2 = map(math.radians, [p1.lat, p1.lon, p2.lat, p2.lon])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            return R * 2 * math.asin(math.sqrt(a))

        unvisited = list(params.places)
        optimized = [unvisited.pop(0)]

        while unvisited:
            current = optimized[-1]
            next_place = min(unvisited, key=lambda p: haversine(current, p))
            optimized.append(next_place)
            unvisited.remove(next_place)

        message = "**Optimized Route**\n"
        for i, p in enumerate(optimized):
            message += f"{i+1}. {p.name}\n"

        return ToolResult(success=True, message=message)

class ItineraryInput(BaseModel):
    destination: str
    days: int
    places: List[str] = Field(default_factory=list)

class GenerateItineraryTool(BaseTool):
    name = "generate_itinerary"
    description = "Generate a structured day-by-day travel itinerary."
    input_schema = ItineraryInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: ItineraryInput) -> ToolResult:
        message = f"**{params.days}-Day Itinerary for {params.destination}**\n\n"
        places = params.places or ["Local sightseeing", "Try local food", "Relax"]

        structured_days = []
        for i in range(params.days):
            place = places[i % len(places)]
            day_plan = f"**Day {i+1}**: {place}"
            message += day_plan + "\n"
            structured_days.append({"day": i+1, "activity": place})

        return ToolResult(
            success=True,
            message=message,
            data={"type": "itinerary", "destination": params.destination, "days": structured_days}
        )
