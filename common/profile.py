"""Cross-agent student profile.

Each agent keeps its own uagents storage for *session* state (last route shown,
last card ids). But what a student tells us about **themselves** — their
college, a step-free preference, the events and clubs they starred — belongs to
the student, not to one agent process. It lives in one shared JSON file so that
saying "I'm at Porter" to any agent teaches all three, and the events agent can
route from the college the navigation agent learned.

Concurrency: three single-threaded agent processes, each writing only on a
student action (a tap), so contention is effectively nil. Writes are atomic via
os.replace, so a race is last-writer-wins on a whole profile — never a corrupt
file. If this ever moves to real multi-user hosting, swap this module for a
proper store; every caller goes through these functions.

`UCSC_PROFILE_PATH` overrides the location (tests point it at a tmp dir).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / ".profiles.json"

VALID_SAVED_KINDS = ("plan", "shortlist")


def _path() -> Path:
    override = os.getenv("UCSC_PROFILE_PATH")
    return Path(override) if override else _DEFAULT_PATH


def _load() -> dict[str, dict[str, Any]]:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt profile file must never take the agents down; students can
        # re-declare their college in one message.
        return {}
    return data if isinstance(data, dict) else {}


def _store(profiles: dict[str, dict[str, Any]]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(profiles, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def get(sender: str) -> dict[str, Any]:
    """The student's profile. A copy — mutate through the setters below."""
    return dict(_load().get(sender, {}))


def _update(sender: str, **fields: Any) -> None:
    profiles = _load()
    profile = profiles.setdefault(sender, {})
    profile.update(fields)
    _store(profiles)


def college(sender: str) -> str | None:
    value = get(sender).get("college")
    return value if isinstance(value, str) and value else None


def set_college(sender: str, name: str) -> None:
    _update(sender, college=name)


def accessible(sender: str) -> bool:
    return bool(get(sender).get("accessible"))


def set_accessible(sender: str, flag: bool) -> None:
    _update(sender, accessible=bool(flag))


def saved(sender: str, kind: str) -> list[str]:
    """Starred item ids, in the order they were saved."""
    assert kind in VALID_SAVED_KINDS, kind
    value = get(sender).get(kind)
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def toggle_saved(sender: str, kind: str, item_id: str) -> bool:
    """Star or unstar an item. Returns True when it is now saved."""
    assert kind in VALID_SAVED_KINDS, kind
    current = saved(sender, kind)
    if item_id in current:
        current = [item for item in current if item != item_id]
        now_saved = False
    else:
        current = current + [item_id]
        now_saved = True
    _update(sender, **{kind: current})
    return now_saved


def clear_saved(sender: str, kind: str) -> None:
    assert kind in VALID_SAVED_KINDS, kind
    _update(sender, **{kind: []})
