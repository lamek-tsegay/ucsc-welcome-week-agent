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
from agents.navigation.service import answer_sibling_query, directions_text
from common import asi1
from common.colleges import by_name
from common.loader import landmark_name
from common.notices import approximate_match_heading
from uagents_core.contrib.protocols.chat import ChatMessage

# "plan my tuesday", "plan tuesday", "itinerary for wednesday", "plan my day"
_PLAN_RE = re.compile(
    r"\b(?:plan|itinerary|schedule)\b.*?\b"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|day)\b",
    re.IGNORECASE,
)

WELCOME = cards.welcome()

# Words that mark a query as this agent's own, exempt from nav bridging.
OWN_DOMAIN_RE = re.compile(r"\b(events?|happening|schedule|plan)\b", re.IGNORECASE)


async def bridge_to_navigation(text: str) -> str | None:
    """Answer a navigation-shaped question typed at this agent, or None."""
    return await answer_sibling_query(text, own_domain=OWN_DOMAIN_RE)

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


async def _walk_legs(events_in_order: list[dict]) -> list[tuple[str, str, int]]:
    """Walking estimates between consecutive events with known venues.

    Times come from the navigation agent's router over the shared campus graph
    — the composition the standalone UCSC pages can't do.
    """
    legs: list[tuple[str, str, int]] = []
    for earlier, later in zip(events_in_order, events_in_order[1:]):
        loc_a = earlier.get("location_id")
        loc_b = later.get("location_id")
        if not loc_a or not loc_b or loc_a == loc_b:
            continue
        walk = await directions_text(loc_a, loc_b)
        if walk is None:
            continue
        minutes_match = re.search(r"About \*\*(\d+) min\*\*", walk)
        if minutes_match:
            legs.append(
                (
                    landmark_name(loc_a),
                    landmark_name(loc_b),
                    int(minutes_match.group(1)),
                )
            )
    return legs


async def respond_to_plan(iso_date: str) -> tuple[ChatMessage, list[str]]:
    """Build the one-day planner: confirmed-first menu plus walking legs."""
    scored, _total = select(EventQuery(dates=[iso_date]), limit=8)
    if not scored:
        return (
            cards.no_matches_message(date_note=None, had_filters=True),
            [],
        )

    legs = await _walk_legs([item.event for item in scored])
    message = cards.planner_message(iso_date, scored, legs)
    return message, [item.event["id"] for item in scored]


async def respond_to_my_plan(event_ids: list[str]) -> tuple[ChatMessage, list[str]]:
    """The student's own starred events, grouped by day with walking legs."""
    chosen = [event for event_id in event_ids if (event := by_id(event_id))]
    if not chosen:
        return cards.empty_plan_message(), []

    # Chronological by date; confirmed first within a day, matching every
    # other listing so placeholders can never lead.
    chosen.sort(key=lambda e: (e["date"], not e["verified"]))

    legs_by_date: dict[str, list[tuple[str, str, int]]] = {}
    for iso in sorted({event["date"] for event in chosen}):
        day_events = [event for event in chosen if event["date"] == iso]
        legs = await _walk_legs(day_events)
        if legs:
            legs_by_date[iso] = legs

    message = cards.my_plan_message(chosen, legs_by_date)
    return message, [event["id"] for event in chosen]


async def directions_to_event(
    event_id: str, college_name: str
) -> ChatMessage | None:
    """Walking directions from a college to an event's venue.

    None when the event or venue is unknown — the caller falls back to an
    honest "can't route yet" message rather than a guess.
    """
    event = by_id(event_id)
    college = by_name(college_name)
    if event is None or college is None:
        return None
    location_id = event.get("location_id")
    if not location_id:
        return None
    if location_id == college.landmark_id:
        return cards.directions_message(
            event, college.name + " College", "You're already there — it's at your college."
        )
    route_text = await directions_text(college.landmark_id, location_id)
    if route_text is None:
        return None
    return cards.directions_message(
        event, landmark_name(college.landmark_id), route_text
    )


async def respond_to_query(text: str, *, today: date) -> tuple[ChatMessage, list[str]]:
    """Answer a free-text events query.

    Returns the reply and the ids shown, so the caller can cache them for card
    taps.
    """
    plan = parse_plan_request(text, today=today)
    if plan is True:
        return cards.day_picker_message(), []
    if isinstance(plan, str):
        return await respond_to_plan(plan)

    query = build_query(text, today)
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


def respond_to_selection(event_id: str, *, saved: bool = False) -> ChatMessage:
    """Answer a card tap. `saved` is the student's ⭐ state for this event."""
    event = by_id(event_id)
    if event is None:
        return cards.stale_selection_message()
    return cards.detail_message(
        event, same_day(event, exclude_id=event_id), saved=saved
    )
