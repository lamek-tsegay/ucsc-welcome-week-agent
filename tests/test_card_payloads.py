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
            selection = node.get("action", {}).get("selection")
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


def test_club_detail_links_are_buttons_not_bubble_text():
    """Links moved onto the card as buttons that open them.

    A URL in message text gets unfurled into a preview card by the client,
    which is why they left the bubble. Every link button also carries a
    selection, so a client that ignores the url sends the tap back and the
    agent replies with the address — a tap can never do nothing.
    """
    from agents.clubs.service import respond_to_selection

    message = respond_to_selection("be_swe")
    assert "http" not in _bubble(message), "a URL in the bubble unfurls a preview"

    urls = _button_urls(_payload(message))
    assert "https://sweclub.engineering.ucsc.edu/" in urls.values()
    assert any("getinvolved.ucsc.edu" in u for u in urls.values())
    assert any(u.startswith("mailto:") for u in urls.values())

    # Every link button still round-trips if the url is ignored.
    def walk(node, out):
        if isinstance(node, dict):
            if node.get("type") == "button" and node["action"].get("url"):
                out.append(node["action"].get("selection"))
            for value in node.values():
                walk(value, out)
        elif isinstance(node, list):
            for entry in node:
                walk(entry, out)

    selections: list = []
    walk(_payload(message), selections)
    assert selections and all(s for s in selections), (
        "a link button with no selection does nothing if the url is ignored"
    )

    # An unverified club has no site of its own but stays reachable.
    urls = _button_urls(_payload(respond_to_selection("c_anime")))
    assert any("getinvolved.ucsc.edu" in u for u in urls.values())


def test_event_detail_offers_a_schedule_link_button():
    """The official schedule is the link this agent owns. Maps and routing
    belong to the navigation agent, so no map links appear here."""
    from agents.events.service import respond_to_selection

    for event_id in ("cornucopia", "choose_your_own_slugventure"):
        message = respond_to_selection(event_id)
        assert "http" not in _bubble(message), event_id
        urls = _button_urls(_payload(message))
        assert any("welcome.ucsc.edu" in u for u in urls.values()), event_id
        assert not any("google.com/maps" in u for u in urls.values()), event_id


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
