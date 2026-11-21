"""Regression tests for schema-driven, non-hardcoded planning."""
from app.agents.universal_planner import UniversalTaskPlanner
from app.tools.registry import registry


class FakeProvider:
    async def _call(self, system, user, force_json=False):
        return "{}"


def planner():
    return UniversalTaskPlanner(provider=FakeProvider(), tool_registry=registry)


def test_required_string_placeholder_is_rejected_generically():
    instance = planner()
    result = instance._build_plan(
        {"steps": [{
            "id": "flight_search",
            "tool": "search_flights_real",
            "params": {
                "origin": "empty",
                "destination": "Somewhere",
                "date": "2027-02-12",
            },
        }]},
        instance._capability_manifest(),
    )
    assert result["decision"] == "clarification"
    assert "placeholder" in result["reply"]


def test_schema_mismatch_is_rejected_using_live_tool_contract():
    instance = planner()
    result = instance._build_plan(
        {"steps": [{
            "id": "hotel_search",
            "tool": "search_hotels_stayapi",
            "params": {
                "destination": "Somewhere",
                "check_in": "2027-02-12",
                "check_out": "2027-02-15",
            },
        }]},
        instance._capability_manifest(),
    )
    assert result["decision"] == "clarification"
    assert "destination" in result["reply"]


def test_missing_inputs_are_not_dropped_from_optional_steps():
    instance = planner()
    result = instance._build_plan(
        {"steps": [{
            "id": "food_search",
            "tool": "discover_food",
            "params": {},
            "required": False,
        }]},
        instance._capability_manifest(),
    )
    assert result["decision"] == "clarification"
    assert "location" in result["reply"]


def test_valid_dynamic_parameters_are_accepted_without_city_specific_rules():
    instance = planner()
    result = instance._build_plan(
        {"steps": [{
            "id": "food_search",
            "tool": "discover_food",
            "params": {"location": "Mysuru", "query": "vegan breakfast"},
            "required": True,
        }]},
        instance._capability_manifest(),
    )
    assert not isinstance(result, dict)
    assert result.steps[0].params["location"] == "Mysuru"
    assert result.steps[0].params["query"] == "vegan breakfast"
