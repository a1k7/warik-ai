import pytest

from app.tools.trip_tools import (
    _allocate_days,
    _allocate_hotel_dates,
)


@pytest.fixture
def kerala_cities():
    return [
        {"name": "Kochi"},
        {"name": "Munnar"},
        {"name": "Alleppey"},
    ]


def test_allocate_days_across_three_cities(kerala_cities):
    result = _allocate_days(kerala_cities, 4)

    assert result == {
        "Kochi": 2,
        "Munnar": 1,
        "Alleppey": 1,
    }

    assert sum(result.values()) == 4


def test_allocate_hotel_dates_for_four_day_trip(kerala_cities):
    per_city = _allocate_days(kerala_cities, 4)

    result = _allocate_hotel_dates(
        cities=kerala_cities,
        per_city=per_city,
        check_in="2026-12-10",
    )

    assert result == [
        {
            "city": "Kochi",
            "check_in": "2026-12-10",
            "check_out": "2026-12-12",
            "nights": 2,
        },
        {
            "city": "Munnar",
            "check_in": "2026-12-12",
            "check_out": "2026-12-13",
            "nights": 1,
        },
        {
            "city": "Alleppey",
            "check_in": "2026-12-13",
            "check_out": "2026-12-14",
            "nights": 1,
        },
    ]


def test_hotel_stays_are_consecutive_without_gaps(kerala_cities):
    per_city = _allocate_days(kerala_cities, 4)

    result = _allocate_hotel_dates(
        cities=kerala_cities,
        per_city=per_city,
        check_in="2026-12-10",
    )

    for current_stay, next_stay in zip(result, result[1:]):
        assert current_stay["check_out"] == next_stay["check_in"]


def test_zero_night_city_is_skipped():
    cities = [
        {"name": "Kochi"},
        {"name": "Munnar"},
        {"name": "Alleppey"},
    ]

    result = _allocate_hotel_dates(
        cities=cities,
        per_city={
            "Kochi": 2,
            "Munnar": 0,
            "Alleppey": 1,
        },
        check_in="2026-12-10",
    )

    assert [stay["city"] for stay in result] == [
        "Kochi",
        "Alleppey",
    ]

    assert result[1]["check_in"] == "2026-12-12"
    assert result[1]["check_out"] == "2026-12-13"


def test_invalid_check_in_date_raises_error(kerala_cities):
    with pytest.raises(ValueError):
        _allocate_hotel_dates(
            cities=kerala_cities,
            per_city={"Kochi": 2, "Munnar": 1, "Alleppey": 1},
            check_in="10-12-2026",
        )
