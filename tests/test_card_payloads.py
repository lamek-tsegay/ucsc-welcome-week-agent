"""Every card payload must use only elements the renderer understands.

An element the ASI:One card renderer does not recognise does not degrade —
the whole card silently fails to render, and the student sees only the text
bubble. That failure looks identical to "the agent didn't send a card", so it
is easy to ship and hard to notice. This module pins the vocabulary against
the reference implementation (innovation-lab-examples/news-card-agent) so a
new element type, heading level, or text style has to be a deliberate choice.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from common.notices import OFFICIAL_CLUBS_URL, OFFICIAL_EVENTS_URL
from uagents_core.contrib.protocols.chat import MetadataContent

# The element-tree schema, from the Agentverse element-tree-primitives docs
# (read 2026-08-12) rather than inferred from one example implementation.
# Getting a value wrong here does not degrade — the whole card silently fails
# to render, which is how a level-4 heading once took every detail card down.
VALID_TYPES = {
    "badge", "button", "choice_grid", "divider", "group", "heading", "image",
    "input", "list", "section", "text",
}
VALID_HEADING_LEVELS = {1, 2, 3}
VALID_TEXT_STYLES = {"body", "muted", "emphasis"}
VALID_DIRECTIONS = {"row", "column"}
VALID_BADGE_VARIANTS = {"info", "success", "warning"}

# Documented validation limit: element-tree nesting depth <= 8.
MAX_NESTING_DEPTH = 8

# Exactly the keys each element accepts. An unrecognised key is not ignored —
# a `url` added to a button's action stopped the entire card rendering, the
# same silent failure an invalid heading level caused. Offline gates cannot
# see it, so the vocabulary is pinned here instead.
ALLOWED_KEYS = {
    "section": {"type", "title", "subtitle", "children"},
    "group": {"type", "direction", "gap", "children"},
    "divider": {"type"},
    "text": {"type", "value", "style"},
    "heading": {"type", "value", "level"},
    "image": {"type", "src", "alt", "aspect_ratio"},
    "badge": {"type", "label", "variant"},
    "button": {"type", "label", "primary", "action"},
    "list": {"type", "items"},
}
ALLOWED_ACTION_KEYS = {"selection", "redirect"}

DURING = date(2026, 9, 22)


def _payload(message) -> dict | None:
    for item in message.content:
        if isinstance(item, MetadataContent):
            return json.loads(item.metadata["card_payload"])
    return None


def _every_card() -> list[tuple[str, dict]]:
    """One payload per card-producing path across all three agents."""
    from agents.clubs import cards as clubs_cards
    from common.loader import clubs as clubs_data
    from agents.clubs.service import (
        respond_to_category,
        respond_to_query as clubs_query,
        respond_to_selection as clubs_selection,
        respond_to_vibe,
    )
    from agents.events import cards as events_cards
    from agents.events.service import (
        respond_to_query as events_query,
        respond_to_selection as events_selection,
    )
    from agents.navigation import cards as nav_cards

    found: list[tuple[str, dict]] = []

    def add(name, message):
        payload = _payload(message)
        if payload is not None:
            found.append((name, payload))

    add("clubs.welcome", clubs_cards.welcome_message())
    add("clubs.interests", clubs_cards.interests_message())
    add("clubs.vibe_picker", clubs_cards.vibe_picker_message())
    add("clubs.all_clubs", clubs_cards.all_clubs_message(list(clubs_data())))
    add("clubs.no_matches", clubs_cards.no_matches_message("zzz"))
    add("clubs.vibe_results", respond_to_vibe("creative")[0])
    add("clubs.category", respond_to_category("tech_engineering")[0])
    add("clubs.detail_unverified", clubs_selection("c_a_cappella"))
    add("clubs.detail_verified", clubs_selection("be_swe"))
    add("clubs.search_results", asyncio.run(clubs_query("clubs about hiking"))[0])

    add("events.welcome", events_cards.welcome_message(None))
    add("events.college_picker", events_cards.college_picker_message())
    add("events.day_picker", events_cards.day_picker_message())
    add("events.listing", asyncio.run(events_query("show me the whole week", today=DURING))[0])
    add("events.detail_confirmed", events_selection("cornucopia"))
    add("events.detail_placeholder", events_selection("ph_porter_arts_night"))

    add("nav.welcome", nav_cards.welcome_message(None))
    add("nav.welcome_with_home", nav_cards.welcome_message("Porter College"))
    add("nav.college_picker", nav_cards.college_picker_message())
    add("nav.step_free_on", nav_cards.step_free_toggled_message(True))

    return found


def _walk(node, visit, path="root"):
    if isinstance(node, dict):
        visit(node, path)
        for key, value in node.items():
            _walk(value, visit, f"{path}.{key}")
    elif isinstance(node, list):
        for index, entry in enumerate(node):
            _walk(entry, visit, f"{path}[{index}]")


ALL_CARDS = _every_card()


def test_the_audit_covers_every_agent():
    """A card path added without a case here would go unchecked."""
    names = {name.split(".")[0] for name, _ in ALL_CARDS}
    assert names == {"clubs", "events", "nav"}
    assert len(ALL_CARDS) >= 20


@pytest.mark.parametrize("name,payload", ALL_CARDS, ids=[n for n, _ in ALL_CARDS])
def test_card_uses_only_renderable_elements(name, payload):
    violations: list[str] = []

    def visit(node, path):
        kind = node.get("type")
        if kind is None:
            return
        if kind not in VALID_TYPES:
            violations.append(f"{path}: unknown element type {kind!r}")
        if kind == "heading" and node.get("level") not in VALID_HEADING_LEVELS:
            violations.append(
                f"{path}: heading level {node.get('level')!r} "
                f"(renderable: {sorted(VALID_HEADING_LEVELS)})"
            )
        if kind == "text":
            style = node.get("style")
            if style is not None and style not in VALID_TEXT_STYLES:
                violations.append(f"{path}: text style {style!r}")
        if kind == "group" and node.get("direction") not in VALID_DIRECTIONS:
            violations.append(f"{path}: group direction {node.get('direction')!r}")
        if kind == "badge" and node.get("variant") not in VALID_BADGE_VARIANTS:
            violations.append(f"{path}: badge variant {node.get('variant')!r}")
        if kind == "button":
            action = node.get("action", {})
            # A button either opens a page or sends a tap back — never both,
            # and never neither.
            if "redirect" in action:
                if "selection" in action:
                    violations.append(f"{path}: button mixes redirect and selection")
                if not str(action["redirect"]).startswith("https://"):
                    violations.append(f"{path}: redirect {action['redirect']!r} is not https")
            else:
                selection = action.get("selection")
                if not isinstance(selection, dict) or not selection:
                    violations.append(f"{path}: button carries no selection payload")

    _walk(payload, visit)
    assert not violations, f"{name}:\n  " + "\n  ".join(violations)


@pytest.mark.parametrize("name,payload", ALL_CARDS, ids=[n for n, _ in ALL_CARDS])
def test_card_has_a_title_and_renders_something(name, payload):
    root = payload["root"]
    assert root["type"] == "section"
    assert root.get("title"), f"{name}: card has no title"
    assert root.get("children"), f"{name}: card has no content"


# --- clickable links ----------------------------------------------------------
# Card `text` elements render plain text: markdown inside them is not
# clickable. The reference implementation works around this by putting its one
# clickable link in the chat bubble, and so do we. These tests pin that split
# so a link never silently becomes unclickable by drifting onto the card.

import re

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((https?://|mailto:)[^)]+\)")


def _bubble(message) -> str:
    from uagents_core.contrib.protocols.chat import TextContent

    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def _button_urls(payload) -> dict[str, str]:
    """Every button that opens a link, as {label: url}."""
    found: dict[str, str] = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button" and node["action"].get("url"):
                found[node["label"]] = node["action"]["url"]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def _selections(payload) -> list[dict]:
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button" and "selection" in node["action"]:
                found.append(node["action"]["selection"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def _redirects(payload) -> set[str]:
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button" and "redirect" in node["action"]:
                found.add(node["action"]["redirect"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def test_club_detail_opens_links_in_one_tap():
    """A link button opens the page itself, via `action.redirect`.

    The url never appears in the bubble, where the client would unfurl it into
    a preview box; it lives on the button, where the tap does the whole job.
    """
    from agents.clubs.service import respond_to_selection

    message = respond_to_selection("be_swe")
    assert "http" not in _bubble(message), "a URL in the bubble unfurls a preview"

    payload = _payload(message)
    redirects = _redirects(payload)
    assert OFFICIAL_CLUBS_URL in redirects, "no button opens the campus directory"
    assert any("swe" in url.lower() for url in redirects), "no button opens the club's own site"

    # Email stays a tap: redirect is documented for pages, and an address is
    # more useful returned as copyable text anyway.
    assert "open_email" in {sel.get("action") for sel in _selections(payload)}

    # An unverified club has no site of its own but stays reachable.
    assert OFFICIAL_CLUBS_URL in _redirects(_payload(respond_to_selection("c_anime")))


def test_event_detail_opens_the_schedule_in_one_tap():
    """The official schedule is the link this agent owns. Maps and routing
    belong to the navigation agent, so no map link appears here."""
    from agents.events.service import respond_to_selection

    for event_id in ("cornucopia", "choose_your_own_slugventure"):
        message = respond_to_selection(event_id)
        assert "http" not in _bubble(message), event_id
        assert OFFICIAL_EVENTS_URL in _redirects(_payload(message)), event_id


def test_listings_carry_no_url_in_the_bubble():
    """The chat client unfurls any URL in message text into a preview box.

    On a listing that box is noise, so listings keep their source pointer on
    the card footnote instead — readable and copyable, but not a link. Detail
    cards make the opposite trade, where tapping through is the point.
    """
    from agents.clubs.service import respond_to_category, respond_to_vibe
    from agents.events.service import (
        respond_to_plan,
        respond_to_query as events_query,
        respond_to_vibe as events_vibe,
    )

    listings = [
        ("clubs vibe", respond_to_vibe("creative")[0]),
        ("clubs category", respond_to_category("tech_engineering")[0]),
        ("events vibe", events_vibe("food")[0]),
        ("events listing", asyncio.run(
            events_query("show me the whole week", today=DURING))[0]),
        ("events planner", respond_to_plan("2026-09-21")[0]),
    ]
    for name, message in listings:
        bubble = _bubble(message)
        assert "http" not in bubble and "mailto:" not in bubble, (
            f"{name}: a URL in the bubble unfurls a preview box"
        )
        # The pointer still travels — on the card.
        assert "http" in json.dumps(_payload(message)), (
            f"{name}: lost its source pointer entirely"
        )


def _depth(node, level: int = 0) -> int:
    if isinstance(node, dict):
        nested = [v for v in node.values() if isinstance(v, (dict, list))]
        return max((_depth(v, level + 1) for v in nested), default=level)
    if isinstance(node, list):
        return max((_depth(v, level) for v in node), default=level)
    return level


@pytest.mark.parametrize("name,payload", ALL_CARDS, ids=[n for n, _ in ALL_CARDS])
def test_card_stays_within_the_nesting_limit(name, payload):
    """The docs cap element-tree nesting at 8 levels.

    Exceeding it is the same class of failure as an unsupported property: the
    payload is valid JSON and every other check passes, but the card does not
    render. The list layouts sit at 6, so there are two levels of headroom —
    worth knowing before anyone wraps rows in another group.
    """
    depth = _depth(payload)
    assert depth <= MAX_NESTING_DEPTH, (
        f"{name}: nests {depth} levels, limit is {MAX_NESTING_DEPTH}"
    )


@pytest.mark.parametrize("name,payload", ALL_CARDS, ids=[n for n, _ in ALL_CARDS])
def test_card_carries_no_unrecognised_keys(name, payload):
    """Every property on every element must be one the schema defines.

    This is the check that would have caught `action.url`, which looked
    harmless — valid JSON, sensible name, a plausible feature — and silently
    took every detail card down until it was noticed in the live client.
    """
    violations: list[str] = []

    def visit(node, path):
        kind = node.get("type")
        if kind in ALLOWED_KEYS:
            extra = set(node) - ALLOWED_KEYS[kind]
            if extra:
                violations.append(f"{path}: {kind} has unknown key(s) {sorted(extra)}")
        if kind == "button":
            action = node.get("action", {})
            extra = set(action) - ALLOWED_ACTION_KEYS
            if extra:
                violations.append(
                    f"{path}: button action has unknown key(s) {sorted(extra)}"
                )

    def walk(node, path="root"):
        if isinstance(node, dict):
            if "type" in node:
                visit(node, path)
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, entry in enumerate(node):
                walk(entry, f"{path}[{index}]")

    walk(payload)
    assert not violations, f"{name}:\n  " + "\n  ".join(violations)
