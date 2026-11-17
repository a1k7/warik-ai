from app.tools import trip_tools
from app.tools.trip_tools import GenerateAdvancedItineraryTool, ItineraryInput


def _city(name, lat, lon):
    return {"name": name, "lat": lat, "lon": lon}


def test_trip_budget_includes_origin_to_destination_as_labeled_estimate(monkeypatch):
    monkeypatch.setattr(
        trip_tools,
        "_geocode_place",
        lambda place: _city("Bhopal", 23.2599, 77.4126),
    )
    tool = GenerateAdvancedItineraryTool()
    params = ItineraryInput(
        destination="Jaipur",
        origin="Bhopal",
        days=3,
        travellers=2,
    )

    budget = tool._compute_budget(
        params,
        [_city("Jaipur", 26.9124, 75.7873)],
    )
    intercity = next(
        item for item in budget.items
        if item.category == "Intercity transport"
    )

    assert intercity.amount is not None
    assert intercity.classification == "ESTIMATE"
    assert "not a train, bus, or flight quote" in intercity.note
    assert "Intercity transport" not in budget.excludes


def test_trip_budget_does_not_silently_estimate_when_origin_cannot_be_resolved(monkeypatch):
    monkeypatch.setattr(trip_tools, "_geocode_place", lambda _place: None)
    tool = GenerateAdvancedItineraryTool()
    params = ItineraryInput(
        destination="Jaipur",
        origin="Unknown Origin",
        days=3,
        travellers=2,
    )

    budget = tool._compute_budget(
        params,
        [_city("Jaipur", 26.9124, 75.7873)],
    )
    intercity = next(
        item for item in budget.items
        if item.category == "Intercity transport"
    )

    assert intercity.amount is None
    assert intercity.classification == "UNAVAILABLE"
    assert "Intercity transport" in budget.excludes
