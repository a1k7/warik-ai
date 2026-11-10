
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult


class FoodOrderInput(BaseModel):
    city: str = Field(
        default="",
        description="City for the search",
    )
    restaurant: str = Field(
        default="",
        description="Restaurant name",
    )
    item: str = Field(
        ...,
        description="Food item to order (e.g., cappuccino, biryani)",
    )


class ZomatoSearchTool(BaseTool):
    name = "search_zomato"

    description = (
        "Generate Zomato and Swiggy food-search links. "
        "Warik cannot place orders directly through these integrations."
    )

    capability = "food_ordering"
    input_schema = FoodOrderInput
    requires_confirmation = False
    is_mutating = False

    provider_adapters = (
        {
            "provider_id": "zomato",
            "display_name": "Zomato",
        },
        {
            "provider_id": "swiggy",
            "display_name": "Swiggy",
        },
    )

    supported_operations = ("link_generation",)

    @staticmethod
    def _query(params: FoodOrderInput) -> str:
        query_parts = [params.item]

        if params.restaurant:
            query_parts.append(f"from {params.restaurant}")

        return " ".join(query_parts)

    @staticmethod
    def _provider_url(
        provider_id: str,
        params: FoodOrderInput,
    ) -> str:
        query = quote(ZomatoSearchTool._query(params))

        if provider_id == "zomato":
            if params.city:
                city_slug = params.city.lower().replace(" ", "-")
                return (
                    f"https://www.zomato.com/{city_slug}/search"
                    f"?q={query}"
                )

            return f"https://www.zomato.com/search?q={query}"

        if provider_id == "swiggy":
            return f"https://www.swiggy.com/search?query={query}"

        raise ValueError(f"Unsupported food provider: {provider_id}")

    @staticmethod
    def _description(params: FoodOrderInput) -> str:
        parts = [f"Order **{params.item}**"]

        if params.restaurant:
            parts.append(f"from **{params.restaurant}**")

        if params.city:
            parts.append(f"in **{params.city}**")

        return " ".join(parts)

    def execute(
        self,
        ctx: ToolContext,
        params: FoodOrderInput,
    ) -> ToolResult:
        description = self._description(params)
        zomato_url = self._provider_url("zomato", params)
        swiggy_url = self._provider_url("swiggy", params)

        return ToolResult(
            success=True,
            message=(
                "I found the right place to complete your order. "
                "Warik cannot place Zomato orders directly yet. "
                "Open a provider link to search and complete "
                f"your order. {description}."
            ),
            data={
                "type": "external_link",
                "title": description,
                "primary": {
                    "label": "Open on Zomato",
                    "url": zomato_url,
                    "provider": "Zomato",
                },
                "secondary": {
                    "label": "Open on Swiggy",
                    "url": swiggy_url,
                    "provider": "Swiggy",
                },
                "disclaimer": (
                    "Warik does not place the order directly. "
                    "Payment and order confirmation happen "
                    "inside the provider's app."
                ),
            },
        )

    def execute_for_provider(
        self,
        ctx: ToolContext,
        params: FoodOrderInput,
        provider_id: str,
    ) -> ToolResult:
        provider_id = str(provider_id).lower()

        if provider_id not in {"zomato", "swiggy"}:
            return ToolResult(
                success=False,
                message=f"Unsupported food provider: {provider_id}",
            )

        provider_name = provider_id.capitalize()
        description = self._description(params)
        url = self._provider_url(provider_id, params)

        return ToolResult(
            success=True,
            message=(
                f"Generated a {provider_name} search link for "
                f"{description}. Warik does not place orders "
                "or process payments."
            ),
            data={
                "type": "external_link",
                "title": description,
                "provider_id": provider_id,
                "primary": {
                    "label": f"Open on {provider_name}",
                    "url": url,
                    "provider": provider_name,
                },
                "disclaimer": (
                    "Warik does not place the order directly. "
                    "Payment and order confirmation happen "
                    "inside the provider's app."
                ),
            },
        )
