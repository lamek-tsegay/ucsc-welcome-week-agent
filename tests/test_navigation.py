"""Navigation resolution, routing, and intent parsing."""

from __future__ import annotations

import asyncio

import pytest

from agents.navigation.parse import (
    KIND_LOCATE,
    KIND_NEARBY,
    KIND_ROUTE,
    parse_patterns,
)
from agents.navigation.resolve import resolve, suggest
from agents.navigation.router import (
    Constraints,
    find_route,
    find_transit,
    nearby,
    should_offer_transit,
)
from agents.navigation.service import answer


# --- resolution ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("McHenry Library", "mchenry_library"),
        ("mchenry", "mchenry_library"),
        ("the bookstore", "bay_tree_bookstore"),
        ("bay tree", "bay_tree_bookstore"),
        ("sci hill", "science_hill"),
        ("OPERS", "opers"),
        ("c10", "john_r_lewis_college"),
        ("college ten", "john_r_lewis_college"),
        ("rachel carson", "rachel_carson_college"),
        ("east upper field", "east_upper_field"),
        ("the boardwalk", "boardwalk"),
    ],
)
def test_resolve_aliases(text, expected):
    match = resolve(text)
    assert match is not None, text
    assert match.landmark_id == expected


@pytest.mark.parametrize(
    "typo,expected",
    [
        ("stevensen", "stevenson_college"),
        ("mchenery", "mchenry_library"),
        ("kresgee", "kresge_college"),
    ],
)
def test_resolve_absorbs_typos(typo, expected):
    match = resolve(typo)
    assert match is not None, typo
    assert match.landmark_id == expected


def test_resolve_returns_none_for_nonsense():
    assert resolve("") is None
    assert resolve("zzzzqqqq") is None


def test_suggest_always_offers_something():
    assert suggest("zzzzqqqq")
    assert len(suggest("porter", limit=3)) <= 3


# --- routing ------------------------------------------------------------------


def test_route_between_neighbours_is_one_step():
    route = find_route("quarry_plaza", "bay_tree_bookstore")
    assert route is not None
    assert len(route.steps) == 1
    assert route.total_minutes == 1


def test_route_identical_endpoints_is_trivial():
    route = find_route("porter_college", "porter_college")
    assert route is not None
    assert route.is_trivial


def test_route_reports_climb_and_descent():
    route = find_route("quarry_plaza", "science_hill")
    assert route is not None
    assert route.total_climb_ft == 185
    assert route.total_descent_ft == 0
    assert route.has_steep


def test_elevation_is_symmetric_on_reverse():
    up = find_route("quarry_plaza", "science_hill")
    down = find_route("science_hill", "quarry_plaza")
    assert up is not None and down is not None
    assert up.total_climb_ft == down.total_descent_ft
    assert up.total_descent_ft == down.total_climb_ft


def test_avoid_hills_changes_the_route():
    direct = find_route("quarry_plaza", "science_hill")
    gentle = find_route("quarry_plaza", "science_hill", Constraints(avoid_hills=True))

    assert direct is not None and gentle is not None
    assert direct.has_steep
    assert not gentle.has_steep
    # The gentler route is genuinely different, and slower.
    assert gentle.total_minutes > direct.total_minutes
    assert [step.to_id for step in gentle.steps] != [step.to_id for step in direct.steps]
    assert not gentle.relaxed_flags


def test_accessible_route_avoids_stairs():
    route = find_route(
        "quarry_plaza", "science_hill", Constraints(accessible=True)
    )
    assert route is not None
    assert not route.has_stairs
    assert not route.has_steep


def test_impossible_constraint_relaxes_and_says_so():
    """Oakes to Science Hill has no steep-free path in the curated graph."""
    route = find_route("oakes_college", "science_hill", Constraints(avoid_hills=True))
    assert route is not None
    assert route.steps, "should still return a walkable route"
    assert "steep" in route.relaxed_flags


def test_relaxed_flags_empty_when_constraint_satisfiable():
    route = find_route(
        "cowell_college", "stevenson_college", Constraints(avoid_hills=True)
    )
    assert route is not None
    assert route.relaxed_flags == []


def test_nearby_is_sorted_and_excludes_self():
    results = nearby("crown_college", limit=4)
    assert results
    assert len(results) <= 4
    minutes = [minutes for _, minutes in results]
    assert minutes == sorted(minutes)
    assert all(name != "Crown College" for name, _ in results)


def test_transit_respects_one_way_direction():
    forward = find_transit("quarry_plaza", "science_hill")
    backward = find_transit("science_hill", "quarry_plaza")
    assert forward is not None
    assert forward.minutes > 0
    # The loop is one-way, so the reverse is not a single ride.
    assert backward is None


def test_transit_absent_when_no_shared_route():
    assert find_transit("oakes_college", "science_hill") is None


def test_should_offer_transit_on_a_climb():
    route = find_route("quarry_plaza", "science_hill")
    assert route is not None
    assert should_offer_transit(route, Constraints())


def test_should_not_offer_transit_for_a_one_minute_stroll():
    route = find_route("quarry_plaza", "bay_tree_bookstore")
    assert route is not None
    assert not should_offer_transit(route, Constraints())


# --- intent parsing -----------------------------------------------------------


def test_parse_from_to():
    intent = parse_patterns("how do I get from Porter to McHenry Library")
    assert intent.kind == KIND_ROUTE
    assert intent.origin and intent.origin.landmark_id == "porter_college"
    assert intent.destination and intent.destination.landmark_id == "mchenry_library"


def test_parse_where_is():
    intent = parse_patterns("where is Quarry Plaza")
    assert intent.kind == KIND_LOCATE
    assert intent.destination and intent.destination.landmark_id == "quarry_plaza"


def test_parse_nearby():
    intent = parse_patterns("what's near Crown College")
    assert intent.kind == KIND_NEARBY
    assert intent.destination and intent.destination.landmark_id == "crown_college"


def test_parse_destination_only():
    intent = parse_patterns("how do I get to the bookstore")
    assert intent.kind == KIND_ROUTE
    assert intent.origin is None
    assert intent.destination and intent.destination.landmark_id == "bay_tree_bookstore"


@pytest.mark.parametrize(
    "phrasing",
    [
        "route from Oakes to Science Hill avoiding hills",
        "from Oakes to Science Hill avoid hills",
        "from Oakes to Science Hill without the hills",
        "gentler route from Oakes to Science Hill",
        "from Oakes to Science Hill, less steep please",
    ],
)
def test_parse_detects_hill_avoidance(phrasing):
    intent = parse_patterns(phrasing)
    assert intent.constraints.avoid_hills, phrasing
    assert intent.destination is not None, phrasing
    assert intent.destination.landmark_id == "science_hill", phrasing


@pytest.mark.parametrize(
    "phrasing",
    [
        "step-free route from Cowell to the bookstore",
        "wheelchair accessible route from Cowell to the bookstore",
        "from Cowell to the bookstore without stairs",
    ],
)
def test_parse_detects_accessibility(phrasing):
    intent = parse_patterns(phrasing)
    assert intent.constraints.accessible, phrasing
    assert intent.destination is not None, phrasing


def test_parse_detects_night():
    intent = parse_patterns("from Porter to Quarry Plaza at night")
    assert intent.constraints.at_night
    assert intent.destination and intent.destination.landmark_id == "quarry_plaza"


def test_constraint_words_do_not_leak_into_place_names():
    """'Science Hill avoiding hills' must still resolve to Science Hill."""
    intent = parse_patterns("from Oakes to Science Hill avoiding hills")
    assert intent.destination_text.strip().lower() == "science hill"


# --- end-to-end answer text ---------------------------------------------------


def _answer(text: str) -> str:
    return asyncio.run(answer(text))


def test_answer_route_mentions_estimate_and_steps():
    reply = _answer("from Cowell to Science Hill")
    assert "Science Hill" in reply
    assert "min" in reply
    assert "estimates" in reply.lower()


def test_answer_asks_for_origin_when_missing():
    reply = _answer("how do I get to the bookstore")
    assert "where are you starting" in reply.lower()


def test_answer_flags_accessibility_uncertainty():
    reply = _answer("step-free route from Cowell to the bookstore")
    assert "Disability Resource Center" in reply


def test_answer_does_not_promise_a_bus_it_cannot_offer():
    """The relaxed-constraint note must not reference a bus that is absent."""
    reply = _answer("route from Oakes to Science Hill avoiding hills")
    assert "no route" in reply.lower()
    if "consider the bus below" in reply:
        assert "Bus alternative" in reply


def test_answer_offers_bus_when_one_exists():
    reply = _answer("wheelchair accessible route from quarry plaza to science hill")
    assert "Bus alternative" in reply
    assert "unverified" in reply.lower()


def test_answer_unknown_query_explains_capabilities():
    reply = _answer("blah blah nonsense")
    assert "Directions" in reply
