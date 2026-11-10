
from app.tools.food_order_tool import FoodOrderInput, ZomatoSearchTool
from app.tools.transport_tool import TransportInput, TransportSearchTool
from app.tools.travel_apis import CabDeepLinkTool, CabInput
from app.tools.base import BaseTool

def test_zomato_execution_returns_only_zomato():
    tool = ZomatoSearchTool()
    params = FoodOrderInput(item="biryani", city="Bhopal")

    result = tool.execute_for_provider(None, params, "zomato")

    assert result.success
    assert result.data["provider_id"] == "zomato"
    assert result.data["primary"]["provider"] == "Zomato"
    assert "zomato.com" in result.data["primary"]["url"]
    assert "secondary" not in result.data


def test_swiggy_execution_returns_only_swiggy():
    tool = ZomatoSearchTool()
    params = FoodOrderInput(item="pizza")

    result = tool.execute_for_provider(None, params, "swiggy")

    assert result.success
    assert result.data["provider_id"] == "swiggy"
    assert result.data["primary"]["provider"] == "Swiggy"
    assert "swiggy.com" in result.data["primary"]["url"]


def test_food_legacy_execution_still_returns_both_providers():
    tool = ZomatoSearchTool()
    params = FoodOrderInput(item="biryani")

    result = tool.execute(None, params)

    assert result.success
    assert result.data["primary"]["provider"] == "Zomato"
    assert result.data["secondary"]["provider"] == "Swiggy"


def test_transport_execution_returns_only_selected_provider():
    tool = TransportSearchTool()
    params = TransportInput(
        origin="Bhopal",
        destination="Delhi",
        date="2026-12-10",
    )

    result = tool.execute_for_provider(None, params, "redbus")

    assert result.success
    assert result.data["provider_id"] == "redbus"
    assert list(result.data["links"]) == ["bus"]
    assert "redbus.in" in result.data["links"]["bus"]


def test_transport_legacy_execution_still_returns_all_links():
    tool = TransportSearchTool()
    params = TransportInput(
        origin="Bhopal",
        destination="Delhi",
        date="2026-12-10",
    )

    result = tool.execute(None, params)

    assert result.success
    assert set(result.data["links"]) == {"train", "bus", "flight"}


def test_cab_execution_returns_only_selected_provider():
    tool = CabDeepLinkTool()
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Railway Station",
    )

    result = tool.execute_for_provider(None, params, "uber")

    assert result.success
    assert result.data["provider_id"] == "uber"
    assert list(result.data["links"]) == ["uber"]
    assert "m.uber.com" in result.data["links"]["uber"]


def test_cab_legacy_execution_still_returns_both_links():
    tool = CabDeepLinkTool()
    params = CabInput(
        pickup_location="VIT Bhopal",
        dropoff_location="Bhopal Railway Station",
    )

    result = tool.execute(None, params)

    assert result.success
    assert set(result.data["links"]) == {"uber", "ola"}


def test_unknown_provider_is_rejected():
    tool = ZomatoSearchTool()
    params = FoodOrderInput(item="biryani")

    result = tool.execute_for_provider(None, params, "unknown")

    assert not result.success


def test_base_tool_refuses_implicit_multi_provider_execution():
    tool = ZomatoSearchTool()
    params = FoodOrderInput(item="biryani")

    result = BaseTool.execute_for_provider(tool, None, params, "zomato")

    assert not result.success
    assert "does not implement provider-specific execution" in result.message


class BaseProviderExecutionProbe(ZomatoSearchTool):
    execute_for_provider = ZomatoSearchTool.__bases__[0].execute_for_provider
