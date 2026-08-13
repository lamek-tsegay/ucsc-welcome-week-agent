"""Event filtering and ranking.

Date handling is the fiddly part. Welcome Week is a fixed six-day window, and
students ask in relative terms ("tonight", "tomorrow", "Wednesday"). Relative
dates are resolved against an injectable reference date so tests are not
dependent on when they run — and so the agent can say something sensible when
asked before the window opens.

Confirmed events outrank placeholder ones. That is a deliberate ranking choice,
not just a display one: the student is better served seeing real events first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from agents_shared.loader import events, events_window

COLLEGES = [
    "Cowell",
    "Stevenson",
    "Crown",
    "Merrill",
    "Porter",
    "Kresge",
    "Oakes",
    "Rachel Carson",
    "College Nine",
    "John R. Lewis",
]

# Colloquial forms students actually type -> canonical college name.
_COLLEGE_ALIASES = {
    "cowell": "Cowell",
    "stevenson": "Stevenson",
    "crown": "Crown",
    "merrill": "Merrill",
    "porter": "Porter",
    "kresge": "Kresge",
    "oakes": "Oakes",
    "rachel carson": "Rachel Carson",
    "carson": "Rachel Carson",
    "college eight": "Rachel Carson",
    "college 8": "Rachel Carson",
    "rcc": "Rachel Carson",
    "college nine": "College Nine",
    "college 9": "College Nine",
    "c9": "College Nine",
    "john r lewis": "John R. Lewis",
    "john r. lewis": "John R. Lewis",
    "lewis": "John R. Lewis",
    "jrl": "John R. Lewis",
    "college ten": "John R. Lewis",
    "college 10": "John R. Lewis",
    "c10": "John R. Lewis",
}

# Free-text interest words -> event tags.
_INTEREST_TAGS = {
    "music": {"music", "arts"},
    "concert": {"music"},
    "band": {"music"},
    "sing": {"music"},
    "art": {"arts"},
    "arts": {"arts"},
    "theater": {"arts"},
    "theatre": {"arts"},
    "dance": {"arts", "music"},
    "sport": {"sports", "recreation"},
    "sports": {"sports", "recreation"},
    "gym": {"sports", "recreation"},
    "athletic": {"sports", "recreation"},
    "fitness": {"sports", "recreation", "wellness"},
    "intramural": {"sports", "recreation"},
    "food": {"food"},
    "eat": {"food"},
    "dinner": {"food"},
    "free food": {"food"},
    "outdoor": {"outdoors"},
    "outdoors": {"outdoors"},
    "hike": {"outdoors"},
    "hiking": {"outdoors"},
    "nature": {"outdoors"},
    "beach": {"offcampus", "outdoors"},
    "ocean": {"offcampus", "outdoors"},
    "social": {"social"},
    "meet people": {"social"},
    "friends": {"social"},
    "party": {"social", "evening"},
    "club": {"orgs"},
    "clubs": {"orgs"},
    "organization": {"orgs"},
    "org": {"orgs"},
    "join": {"orgs"},
    "job": {"career"},
    "jobs": {"career"},
    "work": {"career"},
    "employment": {"career"},
    "career": {"career"},
    "academic": {"academic"},
    "class": {"academic"},
    "major": {"academic"},
    "research": {"academic"},
    "study": {"academic"},
    "library": {"academic"},
    "tech": {"tech"},
    "coding": {"tech"},
    "computer": {"tech"},
    "engineering": {"tech"},
    "cultural": {"cultural"},
    "culture": {"cultural"},
    "identity": {"cultural"},
    "wellness": {"wellness"},
    "yoga": {"wellness"},
    "health": {"wellness"},
    "mental health": {"wellness"},
    "tour": {"tour"},
    "tours": {"tour"},
    "explore": {"tour", "outdoors"},
    "tradition": {"tradition"},
    "photo": {"photo", "tradition"},
    "downtown": {"offcampus"},
    "off campus": {"offcampus"},
    "transfer": {"transfer"},
}

_EVENING_RE = re.compile(r"\b(tonight|evening|night|after\s+dark|late)\b", re.IGNORECASE)

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "weds": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_MONTH_DAY_RE = re.compile(
    r"\b(?:sept(?:ember)?\.?\s*)?(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE
)
_ISO_RE = re.compile(r"\b(2026-09-\d{2})\b")


@dataclass
class DateResolution:
    dates: list[str] = field(default_factory=list)
    note: str | None = None
    asked_relative: bool = False


@dataclass
class EventQuery:
    dates: list[str] = field(default_factory=list)
    college: str | None = None
    tags: set[str] = field(default_factory=set)
    evening_only: bool = False
    date_note: str | None = None
    # True when tags/college came from the ASI:One fallback rather than a
    # direct keyword match, so the reply can say the results are guesses.
    approximate: bool = False


@dataclass
class ScoredEvent:
    event: dict
    score: float
    reasons: list[str] = field(default_factory=list)


def window_dates() -> list[str]:
    return [day["date"] for day in events_window()["days"]]


def weekday_name(iso: str) -> str:
    for day in events_window()["days"]:
        if day["date"] == iso:
            return day["weekday"]
    return date.fromisoformat(iso).strftime("%A")


def _window_bounds() -> tuple[date, date]:
    window = events_window()
    return date.fromisoformat(window["start"]), date.fromisoformat(window["end"])


def resolve_dates(text: str, today: date) -> DateResolution:
    """Work out which Welcome Week days a query is about."""
    lowered = (text or "").lower()
    start, end = _window_bounds()
    valid = set(window_dates())

    iso_match = _ISO_RE.search(lowered)
    if iso_match and iso_match.group(1) in valid:
        return DateResolution(dates=[iso_match.group(1)])

    # Relative terms are only meaningful inside the window.
    if re.search(r"\btoday\b|\btonight\b|\bright now\b", lowered):
        if start <= today <= end:
            return DateResolution(dates=[today.isoformat()], asked_relative=True)
        if today < start:
            days_away = (start - today).days
            return DateResolution(
                dates=[start.isoformat()],
                note=(
                    f"Welcome Week hasn't started yet — it runs "
                    f"{start.strftime('%b %-d')}–{end.strftime('%b %-d')}, "
                    f"{days_away} days from now. Showing the opening day instead."
                ),
                asked_relative=True,
            )
        return DateResolution(
            note=(
                f"Welcome Week finished on {end.strftime('%A %b %-d')}. "
                "I only cover that week."
            ),
            asked_relative=True,
        )

    if re.search(r"\btomorrow\b", lowered):
        target = today + timedelta(days=1)
        if start <= target <= end:
            return DateResolution(dates=[target.isoformat()], asked_relative=True)
        return DateResolution(
            dates=[start.isoformat()],
            note=(
                f"Tomorrow is outside Welcome Week ({start.strftime('%b %-d')}–"
                f"{end.strftime('%b %-d')}). Showing the opening day instead."
            ),
            asked_relative=True,
        )

    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            for iso in window_dates():
                if date.fromisoformat(iso).weekday() == index:
                    return DateResolution(dates=[iso])
            return DateResolution(
                note=(
                    f"There's no {name.title()} in Welcome Week — it runs "
                    f"{start.strftime('%A %b %-d')} to {end.strftime('%A %b %-d')}."
                )
            )

    # A bare day-of-month, e.g. "the 23rd" or "sept 23".
    for match in _MONTH_DAY_RE.finditer(lowered):
        day_number = int(match.group(1))
        if 1 <= day_number <= 31:
            candidate = f"2026-09-{day_number:02d}"
            if candidate in valid:
                return DateResolution(dates=[candidate])
            if 1 <= day_number <= 30:
                return DateResolution(
                    note=(
                        f"September {day_number} is outside Welcome Week "
                        f"({start.strftime('%b %-d')}–{end.strftime('%b %-d')})."
                    )
                )

    if re.search(r"\b(whole|entire|all|full)\s+week\b|\bthe week\b", lowered):
        return DateResolution(dates=window_dates())

    return DateResolution()


def detect_college(text: str) -> str | None:
    lowered = (text or "").lower()
    # Longest alias first so "college nine" wins over "college".
    for alias in sorted(_COLLEGE_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return _COLLEGE_ALIASES[alias]
    return None


def detect_tags(text: str) -> set[str]:
    lowered = (text or "").lower()
    tags: set[str] = set()
    for phrase, mapped in _INTEREST_TAGS.items():
        # Tolerate a plural 's': students type "sports", "tours", "jobs".
        if re.search(rf"\b{re.escape(phrase)}s?\b", lowered):
            tags |= mapped
    return tags


def build_query(text: str, today: date) -> EventQuery:
    """Deterministic query construction from raw user text."""
    resolution = resolve_dates(text, today)
    tags = detect_tags(text)
    evening = bool(_EVENING_RE.search(text or ""))
    if evening:
        tags.add("evening")
    return EventQuery(
        dates=resolution.dates,
        college=detect_college(text),
        tags=tags,
        evening_only=evening,
        date_note=resolution.note,
    )


def _scopes_to(event: dict, college: str | None) -> bool:
    """Whether an event is relevant to a given college."""
    if college is None:
        return True
    scope = event.get("college_scope", "all")
    if scope == "all":
        return True
    if isinstance(scope, list):
        return college in scope
    return scope == college


def select(query: EventQuery, *, limit: int = 8) -> tuple[list[ScoredEvent], int]:
    """Filter and rank events for a query.

    Returns the top `limit` results and the total number that matched, so the
    caller can say when it truncated.

    Confirmed events always sort above placeholder ones — that is the primary
    sort key, not a weight, so no combination of relevance bonuses can float a
    placeholder above a real event. Relevance orders within each group.
    """
    candidates: list[ScoredEvent] = []

    for event in events():
        if query.dates and event["date"] not in query.dates:
            continue
        if not _scopes_to(event, query.college):
            continue

        tags = set(event.get("tags", []))
        overlap = tags & query.tags

        # With interests given, require at least one match — unless the event is
        # college-specific to the college they named, which is relevant anyway.
        college_specific = query.college is not None and isinstance(
            event.get("college_scope"), list
        )
        if query.tags and not overlap and not college_specific:
            continue

        score = 0.0
        reasons: list[str] = []

        if overlap:
            score += 3.0 * len(overlap)
            reasons.append("matches " + ", ".join(sorted(overlap)))
        if college_specific:
            score += 2.5
            reasons.append(f"specific to {query.college}")
        if event.get("verified"):
            reasons.append("officially confirmed")
        if query.evening_only and "evening" in tags:
            score += 1.5

        # Earlier in the week first, as a stable tiebreak.
        score -= window_dates().index(event["date"]) * 0.01

        candidates.append(ScoredEvent(event=event, score=score, reasons=reasons))

    candidates.sort(
        key=lambda scored: (
            not scored.event.get("verified"),  # confirmed first, always
            -scored.score,
            scored.event["date"],
        )
    )
    return candidates[:limit], len(candidates)


def by_id(event_id: str) -> dict | None:
    for event in events():
        if event["id"] == event_id:
            return event
    return None


def same_day(event: dict, *, exclude_id: str, limit: int = 3) -> list[dict]:
    """Other events on the same day, for the detail card."""
    return [
        other
        for other in events()
        if other["date"] == event["date"] and other["id"] != exclude_id
    ][:limit]
