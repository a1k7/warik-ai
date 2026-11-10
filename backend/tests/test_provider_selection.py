
from app.tools.provider_selector import ProviderSelector
from app.tools.registry import ToolRegistry


def test_selects_provider_by_capability_and_operation():
    selector = ProviderSelector(ToolRegistry())

    result = selector.select(
        capability="transport",
        operation="link_generation",
    )

    assert result.available
    assert result.selected is not None
    assert result.selected.provider_id in {"uber", "ola"}


def test_provider_priority_controls_selection():
    selector = ProviderSelector(
        ToolRegistry(),
        provider_priority={"ola": 10, "uber": 20},
    )

    result = selector.select(
        capability="transport",
        operation="link_generation",
    )

    assert result.selected is not None
    assert result.selected.provider_id == "ola"


def test_fallback_skips_failed_provider():
    selector = ProviderSelector(
        ToolRegistry(),
        provider_priority={"uber": 10, "ola": 20},
    )

    result = selector.select(
        capability="transport",
        operation="link_generation",
    )

    assert result.selected is not None
    assert result.selected.provider_id == "uber"

    fallback = result.next_candidate(
        failed_provider_ids={"uber"}
    )

    assert fallback is not None
    assert fallback.provider_id == "ola"
    assert fallback.tool_name == result.selected.tool_name


def test_does_not_select_unsupported_booking_operation():
    selector = ProviderSelector(ToolRegistry())

    result = selector.select(
        capability="transport",
        operation="booking",
    )

    assert not result.available
    assert result.selected is None


def test_does_not_assume_unknown_region_is_global_coverage():
    selector = ProviderSelector(ToolRegistry())

    result = selector.select(
        capability="transport",
        operation="link_generation",
        region="US",
    )

    assert not result.available
    assert result.selected is None


def test_excluded_provider_is_not_selected():
    selector = ProviderSelector(
        ToolRegistry(),
        provider_priority={"uber": 10, "ola": 20},
    )

    result = selector.select(
        capability="transport",
        operation="link_generation",
        exclude_provider_ids={"uber"},
    )

    assert result.selected is not None
    assert result.selected.provider_id == "ola"


def test_flight_search_requires_matching_tool_contract():
    selector = ProviderSelector(ToolRegistry())

    result = selector.select(
        capability="travel",
        operation="search",
        tool_name="search_flights_real",
    )

    assert result.available
    assert result.selected is not None
    assert result.selected.tool_name == "search_flights_real"


def test_hotel_search_is_not_a_fallback_for_flight_search():
    selector = ProviderSelector(ToolRegistry())

    result = selector.select(
        capability="travel",
        operation="search",
        tool_name="search_flights_real",
    )

    assert result.selected is not None

    fallback = result.next_candidate(
        failed_provider_ids={result.selected.provider_id}
    )

    # There is currently no second flight-search provider.
    # A hotel-search tool must never be substituted.
    assert fallback is None


def test_link_generation_selects_transport_link_tool():
    selector = ProviderSelector(ToolRegistry())

    result = selector.select(
        capability="travel",
        operation="link_generation",
        tool_name="search_indian_transport",
    )

    assert result.available
    assert result.selected is not None
    assert result.selected.tool_name == "search_indian_transport"
