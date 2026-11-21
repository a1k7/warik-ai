from pydantic import BaseModel, Field

from app.services.context.travel_recalculation import prepare_recalculation_steps


class _Schema(BaseModel):
    city: str
    check_in: str
    check_out: str
    travellers: int = Field(default=2, ge=1)


class _Tool:
    input_schema = _Schema
    requires_confirmation = False
    is_mutating = False


class _Registry:
    def __init__(self, tools):
        self.tools = tools

    def get(self, name):
        return self.tools.get(name)


def test_hotel_recalculation_uses_saved_validated_query_parameters():
    registry = _Registry({"search_hotels_stayapi": _Tool()})
    mission = {"constraints": {}, "selections": {}, "pending_recalculations": [{
        "queue_id": "q1", "artifact": "hotels", "tool_name": "search_hotels_stayapi",
        "params": {"city": "Goa", "check_in": "2026-12-20", "check_out": "2026-12-23", "travellers": 3},
        "status": "pending",
    }]}
    result = prepare_recalculation_steps(mission, registry)
    assert len(result["steps"]) == 1
    assert result["steps"][0].params["travellers"] == 3
    assert result["blocked"] == []


def test_hotel_recalculation_blocks_when_dates_are_unknown():
    registry = _Registry({"search_hotels_stayapi": _Tool()})
    mission = {"constraints": {"destination": "Goa"}, "selections": {}, "pending_recalculations": [{
        "queue_id": "q2", "artifact": "hotels", "tool_name": "search_hotels_stayapi", "params": {}, "status": "pending",
    }]}
    result = prepare_recalculation_steps(mission, registry)
    assert result["steps"] == []
    assert "check-in" in result["blocked"][0]["reason"]


def test_budget_recalculation_is_local_not_legacy_zero_default_tool():
    mission = {"constraints": {}, "selections": {}, "pending_recalculations": [{
        "queue_id": "q3", "artifact": "budget", "status": "pending", "params": {},
    }]}
    result = prepare_recalculation_steps(mission, _Registry({}))
    assert result["steps"] == []
    assert result["local_completed"] == ["q3"]


def test_route_recalculation_blocks_without_coordinate_backed_places():
    registry = _Registry({"optimize_route": _Tool()})
    mission = {"constraints": {}, "selections": {}, "pending_recalculations": [{
        "queue_id": "q4", "artifact": "routes", "tool_name": "optimize_route", "params": {}, "status": "pending",
    }]}
    result = prepare_recalculation_steps(mission, registry)
    assert result["steps"] == []
    assert "coordinates" in result["blocked"][0]["reason"]


def test_mutating_tool_is_never_auto_dispatched():
    class Mutating(_Tool):
        is_mutating = True

    registry = _Registry({"search_hotels_stayapi": Mutating()})
    mission = {"constraints": {}, "selections": {}, "pending_recalculations": [{
        "queue_id": "q5", "artifact": "hotels", "tool_name": "search_hotels_stayapi",
        "params": {"city": "Goa", "check_in": "2026-12-20", "check_out": "2026-12-23"}, "status": "pending",
    }]}
    result = prepare_recalculation_steps(mission, registry)
    assert result["steps"] == []
    assert "mutating" in result["blocked"][0]["reason"]
