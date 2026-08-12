"""Events query handling, independent of the agent transport."""

from __future__ import annotations

import re
from datetime import date

from agents.events import cards
from agents.events.recommend import (
    EventQuery,
    ScoredEvent,
    build_query,
    by_id,
    detect_college,
    same_day,
    select,
    weekday_name,
    window_dates,
)
from common import asi1
from common.cards import MenuButton
from common.notices import approximate_match_heading
from uagents_core.contrib.protocols.chat import ChatMessage

# "plan my tuesday", "plan tuesday", "itinerary for wednesday", "plan my day"
_PLAN_RE = re.compile(
    r"\b(?:plan|itinerary|schedule)\b.*?\b"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|day)\b",
    re.IGNORECASE,
)

# A general ask with no day, college, or interest in it — the opener that
# should be answered with a question rather than the whole schedule.
_GENERAL_RE = re.compile(
    r"\b(?:welcome\s*week|slug\s*start|what'?s\s+(?:on|happening|going\s+on)"
    r"|tell\s+me\s+about|what\s+(?:is|are)\s+there|events?)\b",
    re.IGNORECASE,
)

WELCOME = cards.welcome()

_SYSTEM_PROMPT = """You extract search filters for a UC Santa Cruz Welcome Week \
events agent. Reply with a single JSON object and nothing else.

Schema:
{
  "tags": [string],
  "college": string or null,
  "evening_only": boolean
}

Allowed tags: social, food, arts, music, outdoors, sports, recreation, wellness,
academic, career, cultural, tech, tradition, evening, offcampus, orgs, tour,
photo, festival, transfer, orientation, jobs.

Colleges: Cowell, Stevenson, Crown, Merrill, Porter, Kresge, Oakes,
Rachel Carson, College Nine, John R. Lewis.

Pick only tags clearly implied by the request. Use an empty list if none are."""

_ALLOWED_TAGS = {
    "social", "food", "arts", "music", "outdoors", "sports", "recreation",
    "wellness", "academic", "career", "cultural", "tech", "tradition", "evening",
    "offcampus", "orgs", "tour", "photo", "festival", "transfer", "orientation",
    "jobs",
}


async def _enrich_with_asi1(text: str, query: EventQuery) -> EventQuery:
    """Fill in interests via ASI:One when the keyword pass found nothing."""
    if query.tags or query.college or not asi1.is_enabled():
        return query

    payload = await asi1.structured(system=_SYSTEM_PROMPT, user=text, max_tokens=180)
    if not payload:
        return query

    raw_tags = payload.get("tags")
    if isinstance(raw_tags, list):
        query.tags |= {
            tag for tag in raw_tags if isinstance(tag, str) and tag in _ALLOWED_TAGS
        }

    college = payload.get("college")
    if isinstance(college, str):
        query.college = detect_college(college) or query.college

    if payload.get("evening_only"):
        query.evening_only = True
        query.tags.add("evening")

    # Anything the model contributed is a guess at what was meant, not a match.
    query.approximate = bool(query.tags or query.college)
    return query


def _heading(
    query: EventQuery,
    scored: list[ScoredEvent],
    total: int,
    query_text: str = "",
) -> str:
    count = len(scored)
    noun = "event" if count == 1 else "events"

    # Results reached only via the ASI:One fallback are guesses. A specific
    # day is still a real filter, so only unanchored queries get relabelled.
    if query.approximate and not query.dates:
        return approximate_match_heading(query_text, count, noun)
    shown = f"{count} {noun}" if count == total else f"top {count} of {total} events"

    if len(query.dates) == 1:
        iso = query.dates[0]
        parsed = date.fromisoformat(iso)
        label = f"{weekday_name(iso)} {parsed.strftime('%b %-d')}"
    elif len(query.dates) == len(window_dates()):
        label = "Welcome Week"
    elif query.dates:
        label = "Selected days"
    else:
        label = "Welcome Week"

    parts = [f"**{label}** — {shown}"]
    if query.college:
        parts.append(f"for {query.college}")
    if query.tags - {"evening"}:
        interests = ", ".join(sorted(query.tags - {"evening"}))
        parts.append(f"matching {interests}")
    return " ".join(parts)


def parse_plan_request(text: str, *, today: date) -> str | None | bool:
    """Detect "plan my Tuesday" style requests.

    Returns an ISO date to plan, True for "plan my day" with no day named
    (caller shows the day picker), or None when this isn't a plan request.
    """
    match = _PLAN_RE.search(text or "")
    if not match:
        return None
    day_word = match.group(1).lower()
    if day_word == "day":
        # "plan my day" during the window means today; outside it, ask.
        today_iso = today.isoformat()
        return today_iso if today_iso in window_dates() else True
    for iso in window_dates():
        if weekday_name(iso).lower() == day_word:
            return iso
    return True


def respond_to_plan(iso_date: str) -> tuple[ChatMessage, list[str]]:
    """The one-day menu: everything on that date, confirmed first."""
    scored, _total = select(EventQuery(dates=[iso_date]), limit=8)
    if not scored:
        return (
            cards.no_matches_message(date_note=None, had_filters=True),
            [],
        )
    return cards.planner_message(iso_date, scored), [
        item.event["id"] for item in scored
    ]


def respond_to_vibe(vibe_key: str) -> tuple[ChatMessage, list[str]] | None:
    """Answer an interest tap. None for an unknown key.

    Interests map to tags rather than a single day, so a student sees what fits
    across the whole week.
    """
    tags = cards.VIBE_TAGS.get(vibe_key)
    if tags is None:
        return None

    scored, total = select(EventQuery(tags=set(tags)))
    if not scored:
        return cards.no_matches_message(date_note=None, had_filters=True), []

    label = cards.VIBE_LABELS[vibe_key]
    count = len(scored)
    noun = "event" if count == 1 else "events"
    shown = f"{count} {noun}" if count == total else f"top {count} of {total} {noun}"
    message = cards.list_message(
        scored,
        heading=f"**{label}** — {shown}",
        date_note=None,
        footer_buttons=[
            MenuButton("🎯 Try another", {"action": "quiz"}),
            MenuButton("📅 Browse by day", {"action": "plan_day"}),
        ],
    )
    return message, [item.event["id"] for item in scored]


async def respond_to_query(text: str, *, today: date) -> tuple[ChatMessage, list[str]]:
    """Answer a free-text events query.

    Returns the reply and the ids shown, so the caller can cache them for card
    taps.
    """
    plan = parse_plan_request(text, today=today)
    if plan is True:
        return cards.day_picker_message(), []
    if isinstance(plan, str):
        return respond_to_plan(plan)

    query = build_query(text, today)

    # A general ask about the week, with no day, college, or interest in it,
    # gets the interests question rather than 22 events at once. A student who
    # already narrowed it ("Wednesday", "free food") skips straight to results.
    if (
        not query.tags
        and not query.college
        and not query.dates
        and _GENERAL_RE.search(text or "")
    ):
        return cards.interests_message(), []

    query = await _enrich_with_asi1(text, query)

    scored, total = select(query)
    if not scored:
        had_filters = bool(query.tags or query.college or query.dates)
        return (
            cards.no_matches_message(
                date_note=query.date_note, had_filters=had_filters
            ),
            [],
        )

    message = cards.list_message(
        scored,
        heading=_heading(query, scored, total, text),
        date_note=query.date_note,
    )
    return message, [item.event["id"] for item in scored]


def respond_to_selection(event_id: str) -> ChatMessage:
    """Answer a card tap."""
    event = by_id(event_id)
    if event is None:
        return cards.stale_selection_message()
    return cards.detail_message(event, same_day(event, exclude_id=event_id))
