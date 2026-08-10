"""Structural integrity of the curated data files.

These are the tests that catch a bad hand-edit: a typo'd landmark id, an event
pointing at a location that does not exist, a disconnected corner of the graph.
"""

from __future__ import annotations

import pytest

from common.loader import (
    club_categories,
    clubs,
    events,
    events_window,
    landmarks,
    transit_routes,
    walk_edges,
)


def test_landmark_ids_unique_and_self_consistent():
    entries = landmarks()
    for landmark_id, entry in entries.items():
        assert entry["id"] == landmark_id
        assert entry["name"]
        assert isinstance(entry.get("aliases", []), list)
        assert entry["lat"] is not None and entry["lon"] is not None
        assert entry["elevation_ft"] is not None


def test_walk_edge_endpoints_exist():
    known = set(landmarks())
    for edge in walk_edges():
        assert edge["from"] in known, f"unknown from: {edge['from']}"
        assert edge["to"] in known, f"unknown to: {edge['to']}"
        assert edge["from"] != edge["to"]


def test_walk_edge_elevation_matches_landmarks():
    """A hand-edited elevation delta that contradicts the landmarks is a bug."""
    entries = landmarks()
    for edge in walk_edges():
        expected = (
            entries[edge["to"]]["elevation_ft"] - entries[edge["from"]]["elevation_ft"]
        )
        assert edge["elev_change_ft"] == expected, (
            f"{edge['from']}->{edge['to']}: elev_change_ft={edge['elev_change_ft']} "
            f"but landmark elevations differ by {expected}"
        )


def test_walk_edges_have_positive_minutes():
    for edge in walk_edges():
        assert edge["minutes"] > 0


def test_every_landmark_is_reachable():
    """The graph must be one connected component, or routing silently fails."""
    adjacency: dict[str, set[str]] = {lid: set() for lid in landmarks()}
    for edge in walk_edges():
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])

    start = "quarry_plaza"
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for neighbour in adjacency[node]:
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)

    unreachable = set(landmarks()) - seen
    assert not unreachable, f"unreachable landmarks: {sorted(unreachable)}"


def test_via_text_is_direction_neutral():
    """Edges are traversed both ways, so 'up'/'down' in `via` reads wrong one way."""
    banned = {"uphill", "downhill"}
    for edge in walk_edges():
        words = set(edge["via"].lower().replace(",", " ").split())
        assert not (words & banned), (
            f"{edge['from']}->{edge['to']} has directional via text: {edge['via']!r}"
        )


def test_transit_stops_exist_and_are_ordered():
    known = set(landmarks())
    for route in transit_routes():
        assert route["stops"], route["id"]
        for stop in route["stops"]:
            assert stop["landmark_id"] in known, stop["landmark_id"]
            assert stop["minutes_from_previous"] >= 0
        assert route["stops"][0]["minutes_from_previous"] == 0


def test_event_locations_exist():
    known = set(landmarks())
    for event in events():
        location_id = event.get("location_id")
        if location_id is not None:
            assert location_id in known, f"{event['id']} -> {location_id}"


def test_event_dates_inside_window():
    valid = {day["date"] for day in events_window()["days"]}
    for event in events():
        assert event["date"] in valid, f"{event['id']} on {event['date']}"


def test_event_ids_unique():
    ids = [event["id"] for event in events()]
    assert len(ids) == len(set(ids))


def test_club_ids_unique_and_categories_known():
    known = {entry["id"] for entry in club_categories()}
    ids = [club["id"] for club in clubs()]
    assert len(ids) == len(set(ids))
    for club in clubs():
        assert club["category"] in known, f"{club['id']} -> {club['category']}"
        assert club["description"]
        assert club.get("tags")


@pytest.mark.parametrize("record_set", ["events", "clubs"])
def test_verified_flag_present_everywhere(record_set):
    records = events() if record_set == "events" else clubs()
    for record in records:
        assert isinstance(record.get("verified"), bool), record["id"]


# Agentverse rejects the entire agent registration if AgentProfile.description
# exceeds 300 characters, and the failure is easy to miss: the agent still runs
# and still serves the chat protocol, it is just never discoverable from ASI:One.
# Read the constants out of the source rather than importing the agent modules,
# which would construct an Agent and bind a port.
AGENTVERSE_DESCRIPTION_LIMIT = 300


def _module_constant(relative_path: str, name: str) -> str:
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent / relative_path
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {relative_path}")


@pytest.mark.parametrize(
    "agent_module",
    [
        "agents/navigation/agent.py",
        "agents/events/agent.py",
        "agents/clubs/agent.py",
    ],
)
def test_agent_description_fits_agentverse_limit(agent_module):
    description = _module_constant(agent_module, "DESCRIPTION")
    assert description, f"{agent_module} has an empty DESCRIPTION"
    assert len(description) <= AGENTVERSE_DESCRIPTION_LIMIT, (
        f"{agent_module}: DESCRIPTION is {len(description)} chars, "
        f"{len(description) - AGENTVERSE_DESCRIPTION_LIMIT} over the Agentverse "
        "limit — registration would fail and the agent would be undiscoverable"
    )


@pytest.mark.parametrize(
    "agent_module",
    [
        "agents/navigation/agent.py",
        "agents/events/agent.py",
        "agents/clubs/agent.py",
    ],
)
def test_agent_readme_carries_discovery_tags(agent_module):
    """The README is the metadata ASI:One's router ranks on, not decoration."""
    readme = _module_constant(agent_module, "README")
    for tag in ("tag:innovationlab", "tag:chatprotocol", "tag:ucsc"):
        assert tag in readme, f"{agent_module} missing {tag}"
