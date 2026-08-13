"""Navigation query handling, independent of the agent transport.

Kept separate from agent.py so tests and the in-process E2E harness can exercise
the full query path without constructing a uAgent (which would open a port and
schedule manifest publication).

Two views of the same pipeline:

- `respond()` is what the agent serves: a card-bearing ChatMessage plus the
  context the agent should remember (last route for one-tap reroutes, the
  anchor for tap-to-walk, a home college the student just declared).
- `answer()` is the plain-text view of the same logic, kept for tests and for
  clients that only read text.

`directions_text()` is the composition seam: the events agent imports it to put
walking directions inside event cards. It is a function import rather than an
agent-to-agent message because all three agents share one data substrate on one
machine — the seam is the service layer, and swapping it for a `ctx.send` to a
remote navigation agent later would change only the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from agents.navigation import cards, render
from agents.navigation.parse import (
    KIND_LOCATE,
    KIND_NEARBY,
    KIND_ROUTE,
    KIND_UNKNOWN,
    NavIntent,
    parse_intent,
    parse_patterns,
)
from agents.navigation.resolve import Match, resolve, suggest
from agents.navigation.router import (
    Constraints,
    find_route,
    find_transit,
    nearby,
    should_offer_transit,
)
from agents_shared.chat import create_text_chat
from agents_shared.colleges import by_key, parse_home_declaration
from agents_shared.loader import landmarks
from uagents_core.contrib.protocols.chat import ChatMessage

WELCOME = render.WELCOME


@dataclass
class NavReply:
    """What the agent should send and what it should remember."""

    message: ChatMessage
    # Last route, so "⛰️ Gentler route" and "what about at night?" can rerun it:
    # {"origin_id", "dest_id", "hills", "stairs", "night"}
    route_ctx: dict | None = None
    # Landmark to walk *from* when the user taps a row in a nearby/locate card.
    anchor_id: str | None = None
    # Home college landmark the user just declared, for the agent to persist.
    home_set: str | None = None
    # Whether the reply used the saved home as a default origin.
    used_home: bool = False
    suppressed: bool = False
    _text: str = field(default="", repr=False)


def _match_for(landmark_id: str) -> Match | None:
    entry = landmarks().get(landmark_id)
    if not entry:
        return None
    return Match(landmark_id, entry["name"], 1.0, "exact")


def _route_reply(intent: NavIntent, *, used_home: bool) -> NavReply:
    assert intent.origin and intent.destination
    route = find_route(
        intent.origin.landmark_id, intent.destination.landmark_id, intent.constraints
    )
    if route is None:
        text = render.render_no_route(intent.origin.name, intent.destination.name)
        return NavReply(message=create_text_chat(text), _text=text)

    transit = None
    if should_offer_transit(route, intent.constraints):
        transit = find_transit(
            intent.origin.landmark_id, intent.destination.landmark_id
        )

    text = render.render_route(intent, route, transit)
    if used_home:
        text += (
            f"\n\n_Starting from **{intent.origin.name}** — your saved college. "
            "Say *I'm at [college]* to change it._"
        )

    if route.is_trivial:
        return NavReply(message=create_text_chat(text), _text=text)

    ctx = {
        "origin_id": intent.origin.landmark_id,
        "dest_id": intent.destination.landmark_id,
        "hills": intent.constraints.avoid_hills,
        "stairs": intent.constraints.accessible,
        "night": intent.constraints.at_night,
    }
    message = cards.route_message(
        text, route=route, constraints=intent.constraints, reversible=True
    )
    return NavReply(
        message=message,
        route_ctx=ctx,
        anchor_id=intent.destination.landmark_id,
        used_home=used_home,
        _text=text,
    )


def _nearby_reply(landmark_id: str) -> NavReply:
    neighbours = nearby(landmark_id)  # [(name, minutes)]
    text = render.render_nearby(landmark_id, neighbours)
    if not neighbours:
        return NavReply(message=create_text_chat(text), _text=text)

    # nearby() returns (name, minutes); rows need ids for route_to buttons.
    names_to_ids = {entry["name"]: lid for lid, entry in landmarks().items()}
    rows = [
        (names_to_ids.get(name, ""), name, minutes)
        for name, minutes in neighbours
        if names_to_ids.get(name)
    ]
    message = cards.nearby_message(text, rows)
    return NavReply(message=message, anchor_id=landmark_id, _text=text)


def _locate_reply(landmark_id: str, *, has_home: bool) -> NavReply:
    text = render.render_locate(landmark_id)
    name = landmarks()[landmark_id]["name"]
    message = cards.locate_message(
        text, landmark_id=landmark_id, name=name, has_home=has_home
    )
    return NavReply(message=message, anchor_id=landmark_id, _text=text)


def _merged_constraints(last_route: dict, fresh: Constraints) -> Constraints:
    return Constraints(
        avoid_hills=last_route.get("hills", False) or fresh.avoid_hills,
        accessible=last_route.get("stairs", False) or fresh.accessible,
        at_night=last_route.get("night", False) or fresh.at_night,
    )


def reroute(last_route: dict, mode: str) -> NavReply | None:
    """Rerun the remembered route with one changed condition. None if unusable."""
    origin_id = last_route.get("origin_id")
    dest_id = last_route.get("dest_id")
    if mode == "reverse":
        origin_id, dest_id = dest_id, origin_id
    origin, destination = _match_for(origin_id or ""), _match_for(dest_id or "")
    if not origin or not destination:
        return None

    constraints = Constraints(
        avoid_hills=last_route.get("hills", False) or mode == "hills",
        accessible=last_route.get("stairs", False) or mode == "stairs",
        at_night=last_route.get("night", False) or mode == "night",
    )
    intent = NavIntent(
        kind=KIND_ROUTE, origin=origin, destination=destination, constraints=constraints
    )
    return _route_reply(intent, used_home=False)


def route_between(origin_id: str, dest_id: str) -> NavReply | None:
    """Route two known landmarks — used by tap-to-walk and by the events agent."""
    origin, destination = _match_for(origin_id), _match_for(dest_id)
    if not origin or not destination:
        return None
    intent = NavIntent(kind=KIND_ROUTE, origin=origin, destination=destination)
    return _route_reply(intent, used_home=False)


async def directions_text(origin_id: str, dest_id: str) -> str | None:
    """Plain-text walking directions between two landmark ids, or None.

    The seam the events agent composes through: same router, same honesty
    labels, no duplicate rendering logic.
    """
    reply = route_between(origin_id, dest_id)
    return reply._text if reply else None


def try_home_declaration(text: str) -> tuple[str, str] | None:
    """If the text is "I'm at X" and X resolves, return (landmark_id, name)."""
    place = parse_home_declaration(text)
    if not place:
        return None
    # Accept a college key from a card tap ("porter") or free text ("Porter").
    college = by_key(place.replace(" ", "_"))
    if college:
        return college.landmark_id, landmarks()[college.landmark_id]["name"]
    match = resolve(place)
    if match and match.how in {"exact", "substring"}:
        return match.landmark_id, match.name
    return None


async def respond(
    text: str,
    *,
    home_id: str | None = None,
    last_route: dict | None = None,
    always_accessible: bool = False,
) -> NavReply:
    """Produce the full reply for a navigation query.

    `always_accessible` is the student's saved step-free preference: every
    route request behaves as though they had typed "step-free", without them
    having to remember to. Asking explicitly still works and is identical.
    """
    declared = try_home_declaration(text)
    if declared:
        landmark_id, name = declared
        nearby_reply = _nearby_reply(landmark_id)
        message = cards.home_saved_message(name, nearby_reply._text)
        return NavReply(message=message, home_set=landmark_id, anchor_id=landmark_id)

    intent = await parse_intent(text)
    if always_accessible and not intent.constraints.accessible:
        intent = replace(
            intent, constraints=replace(intent.constraints, accessible=True)
        )

    if intent.kind == KIND_LOCATE and intent.destination:
        return _locate_reply(
            intent.destination.landmark_id, has_home=home_id is not None
        )

    if intent.kind == KIND_NEARBY and intent.destination:
        return _nearby_reply(intent.destination.landmark_id)

    if intent.kind == KIND_ROUTE:
        if not intent.destination:
            query = intent.destination_text or text
            text_out = render.render_unresolved(query, suggest(query))
            return NavReply(message=create_text_chat(text_out), _text=text_out)

        used_home = False
        if not intent.origin:
            if intent.origin_text:
                text_out = render.render_unresolved(
                    intent.origin_text, suggest(intent.origin_text)
                )
                return NavReply(message=create_text_chat(text_out), _text=text_out)
            if home_id and home_id != intent.destination.landmark_id:
                home_match = _match_for(home_id)
                if home_match:
                    intent = replace(intent, origin=home_match)
                    used_home = True
            if not intent.origin:
                text_out = render.render_need_origin(intent.destination.name)
                message = cards.locate_message(
                    text_out,
                    landmark_id=intent.destination.landmark_id,
                    name=intent.destination.name,
                    has_home=home_id is not None,
                )
                return NavReply(
                    message=message,
                    anchor_id=intent.destination.landmark_id,
                    _text=text_out,
                )

        return _route_reply(intent, used_home=used_home)

    # A bare follow-up like "what about at night?" applies new constraints to
    # the remembered route instead of hitting the unknown-query wall.
    if intent.constraints.any_set and last_route:
        constraints = _merged_constraints(last_route, intent.constraints)
        origin = _match_for(last_route.get("origin_id", ""))
        destination = _match_for(last_route.get("dest_id", ""))
        if origin and destination:
            follow_up = NavIntent(
                kind=KIND_ROUTE,
                origin=origin,
                destination=destination,
                constraints=constraints,
            )
            return _route_reply(follow_up, used_home=False)

    text_out = render.render_unknown(text, suggest(text))
    return NavReply(message=create_text_chat(text_out), _text=text_out)


async def answer(text: str) -> str:
    """Plain-text view of `respond`, for tests and text-only clients."""
    reply = await respond(text)
    if reply._text:
        return reply._text
    # Home declarations and other card-first replies: fall back to the bubble.
    for item in reply.message.content:
        if hasattr(item, "text"):
            return item.text
    return ""


# --- cross-agent bridging ----------------------------------------------------
# Students don't know which agent owns what. A navigation-shaped question typed
# at the events or clubs agent should just get answered; an events-shaped
# question typed here should get a useful hand-off, not a shrug.

NAV_SHAPED_RE = re.compile(
    r"\b(where\s+is|where'?s|how\s+do\s+i\s+get|how\s+far|route|directions?"
    r"|walk(?:ing)?\s+to|near(?:by)?|get\s+to)\b",
    re.IGNORECASE,
)

_SIBLING_NOTE = (
    "\n\n_(That answer came from my sibling — for reroutes and more, ask "
    "**UCSC Campus Navigation**.)_"
)

EVENTS_SHAPED_RE = re.compile(
    r"\b(what'?s\s+(on|happening)|events?\b|happening\b|tonight\b|tomorrow\b"
    r"|this\s+week\b|schedule\b|free\s+food)\b",
    re.IGNORECASE,
)


async def answer_sibling_query(
    text: str, *, own_domain: re.Pattern[str]
) -> str | None:
    """Navigation answer for another agent's inbound text, or None.

    Gated three ways so it can never hijack a domain query: the text must use
    an explicit navigation phrase, must not mention the calling agent's own
    domain, and must resolve to a real landmark with high confidence ("where
    is the party" fuzzy-matching Porter must not become a locate).
    """
    if not NAV_SHAPED_RE.search(text) or own_domain.search(text):
        return None
    intent = parse_patterns(text)
    if intent.kind not in {KIND_ROUTE, KIND_LOCATE, KIND_NEARBY}:
        return None
    if intent.destination is None or intent.destination.how not in {
        "exact",
        "substring",
    }:
        return None
    reply = await respond(text)
    if not reply._text:
        return None
    return reply._text + _SIBLING_NOTE


def events_pointer(text: str) -> str | None:
    """Hand-off for events questions the navigation parser can't answer."""
    if not EVENTS_SHAPED_RE.search(text):
        return None
    if parse_patterns(text).kind != KIND_UNKNOWN:
        return None
    try:  # The events agent ships separately; without it, event-name
        # destinations simply don't resolve and the caller says so.
        from agents.events.recommend import EventQuery, select
    except ImportError:  # standalone navigation deployment
        return None

    confirmed, _ = select(EventQuery(), limit=3)
    teaser = "\n".join(
        f"• **{item.event['title']}**"
        for item in confirmed
        if item.event["verified"]
    )
    return (
        "That sounds like an events question — I'm the navigation agent. 🗺️\n\n"
        "Ask **UCSC Welcome Week Events** for the full schedule, planner, and "
        "college filtering. A peek at the confirmed headliners:\n\n"
        f"{teaser}\n\n"
        "I can get you to any of those venues — *how do I get to Cornucopia*."
    )
