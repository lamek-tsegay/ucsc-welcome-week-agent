"""Data loading seam.

Every agent reads its data through this module. Swapping the curated seed files
in `data/` for real UCSC exports means changing these loaders only — no agent
logic touches the filesystem directly.

Files are read once and cached, since none of them change while an agent runs.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=None)
def landmarks() -> dict[str, dict[str, Any]]:
    """All campus landmarks, keyed by id."""
    return {item["id"]: item for item in _read("landmarks.json")["landmarks"]}


@lru_cache(maxsize=None)
def landmarks_meta() -> dict[str, Any]:
    return _read("landmarks.json")["_meta"]


@lru_cache(maxsize=None)
def walk_edges() -> list[dict[str, Any]]:
    """Raw undirected walking edges. The router expands these both ways."""
    return _read("walk_graph.json")["edges"]


@lru_cache(maxsize=None)
def transit_routes() -> list[dict[str, Any]]:
    return _read("transit.json")["routes"]


@lru_cache(maxsize=None)
def transit_meta() -> dict[str, Any]:
    return _read("transit.json")["_meta"]


@lru_cache(maxsize=None)
def events() -> list[dict[str, Any]]:
    return _read("events.json")["events"]


@lru_cache(maxsize=None)
def events_window() -> dict[str, Any]:
    """The Welcome Week date window: start, end, label, and per-day weekdays."""
    return _read("events.json")["window"]


@lru_cache(maxsize=None)
def events_meta() -> dict[str, Any]:
    return _read("events.json")["_meta"]


@lru_cache(maxsize=None)
def clubs() -> list[dict[str, Any]]:
    return _read("clubs.json")["clubs"]


@lru_cache(maxsize=None)
def club_categories() -> list[dict[str, Any]]:
    return _read("clubs.json")["categories"]


@lru_cache(maxsize=None)
def clubs_meta() -> dict[str, Any]:
    return _read("clubs.json")["_meta"]


def landmark_name(landmark_id: str | None, fallback: str = "an unlisted location") -> str:
    """Human-readable name for a landmark id, tolerant of nulls."""
    if not landmark_id:
        return fallback
    entry = landmarks().get(landmark_id)
    return entry["name"] if entry else fallback
