from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from urllib.parse import quote

class FoodOrderInput(BaseModel):
    city: str = Field(default="", description="City for the search")
    restaurant: str = Field(default="", description="Restaurant name")
    item: str = Field(..., description="Food item to order (e.g., cappuccino, biryani)")

class ZomatoSearchTool(BaseTool):
    name = "search_zomato"
    description = "Generate a Zomato deep link to order food. Warik cannot place orders directly, so this provides an external handoff."
    capability = "food_ordering"
    input_schema = FoodOrderInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: FoodOrderInput) -> ToolResult:
        # Build a search query
        query_parts = [params.item]
        if params.restaurant:
            query_parts.append(f"from {params.restaurant}")
        query = " ".join(query_parts)

        # Build the Zomato URL
        if params.city:
            city_slug = params.city.lower().replace(" ", "-")
            search_url = f"https://www.zomato.com/{city_slug}/search?q={quote(query)}"
        else:
            search_url = f"https://www.zomato.com/search?q={quote(query)}"

        # Also build a Swiggy fallback
        swiggy_url = f"https://www.swiggy.com/search?query={quote(query)}"

        description_parts = [f"Order **{params.item}**"]
        if params.restaurant:
            description_parts.append(f"from **{params.restaurant}**")
        if params.city:
            description_parts.append(f"in **{params.city}**")
        description = " ".join(description_parts)

        return ToolResult(
            success=True,
            message=(
                f"I found the right place to complete your order. "
                f"Since I can't place Zomato orders directly yet, please tap below to search "
                f"and complete the order on Zomato. {description}."
            ),
            data={
                "type": "external_link",
                "title": description,
                "primary": {
                    "label": "Open on Zomato",
                    "url": search_url,
                    "provider": "Zomato",
                },
                "secondary": {
                    "label": "Open on Swiggy",
                    "url": swiggy_url,
                    "provider": "Swiggy",
                },
                "disclaimer": "Warik cannot place the order directly. Payment will be completed on the provider's app.",
            }
        )