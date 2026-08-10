"""Routing over the curated campus walking graph.

The `minutes` on each edge already account for that path's terrain, so elevation
is *not* added as a cost by default — that would double-count the climb. Elevation
instead drives reporting, and becomes a cost only when the student asks to avoid
hills.

Constraints are applied as hard exclusions first. If excluding makes the
destination unreachable, we route anyway and say so, because "no route" is a
worse answer than "here's the route, but it has stairs".
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from common.loader import landmarks, transit_routes, walk_edges


@dataclass(frozen=True)
class Constraints:
    avoid_hills: bool = False
    accessible: bool = False
    at_night: bool = False

    @property
    def any_set(self) -> bool:
        return self.avoid_hills or self.accessible or self.at_night


@dataclass
class Step:
    from_id: str
    to_id: str
    from_name: str
    to_name: str
    minutes: int
    elev_change_ft: int
    flags: list[str]
    via: str


@dataclass
class Route:
    steps: list[Step]
    total_minutes: int
    total_climb_ft: int
    total_descent_ft: int
    relaxed_flags: list[str] = field(default_factory=list)

    @property
    def is_trivial(self) -> bool:
        return not self.steps

    @property
    def flags_present(self) -> set[str]:
        return {flag for step in self.steps for flag in step.flags}

    @property
    def has_steep(self) -> bool:
        return "steep" in self.flags_present

    @property
    def has_stairs(self) -> bool:
        return "stairs" in self.flags_present


@dataclass
class TransitOption:
    route_id: str
    route_name: str
    board_at: str
    alight_at: str
    minutes: int
    stops: int
    note: str


def _adjacency() -> dict[str, list[dict]]:
    """Expand undirected edges into a directed adjacency map."""
    graph: dict[str, list[dict]] = {}
    for edge in walk_edges():
        forward = {
            "to": edge["to"],
            "minutes": edge["minutes"],
            "elev_change_ft": edge["elev_change_ft"],
            "flags": list(edge.get("flags", [])),
            "via": edge.get("via", ""),
        }
        backward = {
            "to": edge["from"],
            "minutes": edge["minutes"],
            "elev_change_ft": -edge["elev_change_ft"],
            "flags": list(edge.get("flags", [])),
            "via": edge.get("via", ""),
        }
        graph.setdefault(edge["from"], []).append(forward)
        graph.setdefault(edge["to"], []).append(backward)
    return graph


def _excluded_flags(constraints: Constraints) -> set[str]:
    excluded: set[str] = set()
    if constraints.avoid_hills:
        excluded.add("steep")
    if constraints.accessible:
        excluded.update({"stairs", "steep"})
    return excluded


def _cost(edge: dict, constraints: Constraints) -> float:
    cost = float(edge["minutes"])
    if constraints.avoid_hills:
        climb = max(0, edge["elev_change_ft"])
        cost += climb / 25.0
    if constraints.at_night and "unlit" in edge["flags"]:
        cost += 5.0
    if constraints.accessible and "paved" in edge["flags"]:
        cost -= 0.5
    return max(cost, 0.1)


def _dijkstra(
    origin: str, destination: str, constraints: Constraints, excluded: set[str]
) -> list[Step] | None:
    graph = _adjacency()
    if origin not in graph or destination not in graph:
        return None

    names = {lid: entry["name"] for lid, entry in landmarks().items()}
    best: dict[str, float] = {origin: 0.0}
    previous: dict[str, tuple[str, dict]] = {}
    queue: list[tuple[float, str]] = [(0.0, origin)]
    settled: set[str] = set()

    while queue:
        cost_so_far, node = heapq.heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        if node == destination:
            break

        for edge in graph.get(node, []):
            if excluded & set(edge["flags"]):
                continue
            neighbour = edge["to"]
            if neighbour in settled:
                continue
            candidate = cost_so_far + _cost(edge, constraints)
            if candidate < best.get(neighbour, float("inf")):
                best[neighbour] = candidate
                previous[neighbour] = (node, edge)
                heapq.heappush(queue, (candidate, neighbour))

    if destination not in settled:
        return None

    steps: list[Step] = []
    cursor = destination
    while cursor != origin:
        prior, edge = previous[cursor]
        steps.append(
            Step(
                from_id=prior,
                to_id=cursor,
                from_name=names.get(prior, prior),
                to_name=names.get(cursor, cursor),
                minutes=edge["minutes"],
                elev_change_ft=edge["elev_change_ft"],
                flags=edge["flags"],
                via=edge["via"],
            )
        )
        cursor = prior
    steps.reverse()
    return steps


def find_route(
    origin: str, destination: str, constraints: Constraints | None = None
) -> Route | None:
    """Best route, honouring constraints where possible.

    Returns None only if the two landmarks are genuinely disconnected in the
    graph. If constraints made it unreachable, the route comes back with
    `relaxed_flags` naming what we could not avoid.
    """
    constraints = constraints or Constraints()

    if origin == destination:
        return Route(steps=[], total_minutes=0, total_climb_ft=0, total_descent_ft=0)

    excluded = _excluded_flags(constraints)
    steps = _dijkstra(origin, destination, constraints, excluded)
    relaxed: list[str] = []

    if steps is None and excluded:
        steps = _dijkstra(origin, destination, constraints, set())
        relaxed = sorted(excluded)

    if steps is None:
        return None

    climb = sum(step.elev_change_ft for step in steps if step.elev_change_ft > 0)
    descent = -sum(step.elev_change_ft for step in steps if step.elev_change_ft < 0)

    # If we relaxed but the resulting route happens to avoid the flags anyway,
    # there is nothing to warn about.
    present = {flag for step in steps for flag in step.flags}
    relaxed = [flag for flag in relaxed if flag in present]

    return Route(
        steps=steps,
        total_minutes=sum(step.minutes for step in steps),
        total_climb_ft=climb,
        total_descent_ft=descent,
        relaxed_flags=relaxed,
    )


def find_transit(origin: str, destination: str) -> TransitOption | None:
    """A single-route bus ride between two landmarks, if one exists.

    No transfers: a suggestion a new student can actually follow. Direction
    matters, since the campus loop is one-way.
    """
    best: TransitOption | None = None
    names = {lid: entry["name"] for lid, entry in landmarks().items()}

    for route in transit_routes():
        stops = [stop["landmark_id"] for stop in route["stops"]]
        if origin not in stops or destination not in stops:
            continue
        start, end = stops.index(origin), stops.index(destination)
        if start >= end:
            continue

        minutes = sum(
            route["stops"][index]["minutes_from_previous"]
            for index in range(start + 1, end + 1)
        )
        option = TransitOption(
            route_id=route["id"],
            route_name=route["name"],
            board_at=names.get(origin, origin),
            alight_at=names.get(destination, destination),
            minutes=minutes,
            stops=end - start,
            note=route.get("note", ""),
        )
        if best is None or option.minutes < best.minutes:
            best = option

    return best


def should_offer_transit(route: Route, constraints: Constraints) -> bool:
    """Whether a bus alternative is worth mentioning.

    On this campus the honest answer to "avoid the hills" is often "take the bus",
    so we surface it whenever the walk is a real climb or a long haul.
    """
    if route.is_trivial:
        return False
    return (
        route.has_steep
        or route.total_climb_ft >= 100
        or route.total_minutes >= 20
        or constraints.avoid_hills
        or constraints.accessible
        or bool(route.relaxed_flags)
    )


def nearby(landmark_id: str, limit: int = 5) -> list[tuple[str, int]]:
    """(name, minutes) for the closest landmarks by walking time."""
    graph = _adjacency()
    if landmark_id not in graph:
        return []

    names = {lid: entry["name"] for lid, entry in landmarks().items()}
    best: dict[str, float] = {landmark_id: 0.0}
    queue: list[tuple[float, str]] = [(0.0, landmark_id)]
    settled: set[str] = set()

    while queue:
        cost, node = heapq.heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        for edge in graph.get(node, []):
            candidate = cost + edge["minutes"]
            if candidate < best.get(edge["to"], float("inf")):
                best[edge["to"]] = candidate
                heapq.heappush(queue, (candidate, edge["to"]))

    ordered = sorted(
        ((names.get(lid, lid), int(round(minutes))) for lid, minutes in best.items() if lid != landmark_id),
        key=lambda pair: pair[1],
    )
    return ordered[:limit]
