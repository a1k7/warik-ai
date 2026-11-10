
from app.tools.registry import ToolRegistry


def test_existing_registry_methods_remain_compatible():
    registry = ToolRegistry()

    assert registry.get("search_flights_real") is not None
    assert registry.get("search_hotels_stayapi") is not None
    assert "search_indian_transport" in registry.list_tools()


def test_transport_tool_is_registered_as_link_generation():
    registry = ToolRegistry()

    tool = registry.get("search_indian_transport")

    assert tool is not None
    assert tool.capability == "travel"
    assert "link_generation" in tool.supported_operations


def test_cab_tool_does_not_claim_booking_operation():
    registry = ToolRegistry()

    tool = registry.get("get_cab_links")

    assert tool is not None
    assert "link_generation" in tool.supported_operations
    assert "booking" not in tool.supported_operations


def test_food_tool_does_not_claim_order_placement():
    registry = ToolRegistry()

    tool = registry.get("search_zomato")

    assert tool is not None
    assert "link_generation" in tool.supported_operations
    assert "order_placement" not in tool.supported_operations


def test_provider_manifest_contains_registered_adapters():
    registry = ToolRegistry()

    providers = registry.describe_providers()

    provider_ids = {
        item["provider_id"]
        for item in providers
    }

    assert {
        "uber",
        "ola",
        "zomato",
        "swiggy",
    }.issubset(provider_ids)

    assert {
        "irctc",
        "redbus",
        "makemytrip",
    }.issubset(provider_ids)


def test_find_tools_filters_by_capability_and_operation():
    registry = ToolRegistry()

    tools = registry.find_tools(
        capability="transport",
        operation="link_generation",
    )

    names = {
        tool.name
        for tool in tools
    }

    assert "get_cab_links" in names
    assert "search_indian_transport" not in names


def test_region_filter_does_not_assume_global_coverage():
    registry = ToolRegistry()

    tools = registry.find_tools(
        capability="transport",
        operation="link_generation",
        region="US",
    )

    assert tools == []


def test_planner_manifest_contains_provider_metadata():
    registry = ToolRegistry()

    manifest = registry.describe_tools()

    transport = next(
        item
        for item in manifest
        if item["name"] == "get_cab_links"
    )

    assert transport["capability"] == "transport"

    assert transport["supported_operations"] == [
        "link_generation"
    ]

    assert {
        item["provider_id"]
        for item in transport["provider_adapters"]
    } == {
        "uber",
        "ola",
    }
