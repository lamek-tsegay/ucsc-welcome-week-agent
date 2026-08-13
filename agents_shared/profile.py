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
