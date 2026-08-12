"""Generic ASI:One interactive card builders.

Cards are Agentverse "element tree" payloads carried on a `MetadataContent`
block alongside a plain text bubble. The structure here follows
innovation-lab-examples/news-card-agent/cards.py and the docs at
https://docs.agentverse.ai/documentation/advanced-usages/agent-driven-interactive-cards

Generalised over record type so the events and clubs agents share one
implementation. No images: we have no verified image URLs for UCSC events or
organizations, and pointing at guessed URLs would render broken cards.

Text bubbles accompany every card deliberately. A client that does not render
cards still shows something useful, so the agents stay usable outside ASI:One.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    MetadataContent,
    TextContent,
)

from common.chat import utc_now

CARD_PROTOCOL_VERSION = "1"

# Badge variants the UI understands. "warning" is what we use to mark
# unverified records, so they are visually distinct, not just distinct in prose.
BADGE_INFO = "info"
BADGE_WARNING = "warning"
BADGE_SUCCESS = "success"


@dataclass
class CardItem:
    """One row in a list card."""

    record_id: str
    heading: str
    body: str
    badges: list[tuple[str, str]] = field(default_factory=list)
    button_label: str = "See details"


@dataclass
class DetailRow:
    """One label/value line in a detail card."""

    label: str
    value: str


@dataclass
class MenuButton:
    """One tappable action button.

    `selection` is what comes back when the user taps — the same dict shape the
    list/detail buttons already use, so `parse_card_selection` handles all of
    them uniformly. `source` is injected at build time.
    """

    label: str
    selection: dict[str, str]
    primary: bool = False


def _badge(label: str, variant: str) -> dict[str, Any]:
    return {"type": "badge", "label": label, "variant": variant}


def _button(button: MenuButton, source: str) -> dict[str, Any]:
    selection = dict(button.selection)
    selection.setdefault("source", source)
    return {
        "type": "button",
        "label": button.label,
        "primary": button.primary,
        "action": {"selection": selection},
    }


def _button_rows(
    buttons: list[MenuButton], source: str, *, per_row: int = 3
) -> list[dict[str, Any]]:
    """Buttons chunked into row groups so long menus wrap instead of squeezing."""
    rows: list[dict[str, Any]] = []
    for start in range(0, len(buttons), per_row):
        rows.append(
            {
                "type": "group",
                "direction": "row",
                "gap": 8,
                "children": [
                    _button(button, source)
                    for button in buttons[start : start + per_row]
                ],
            }
        )
    return rows


def build_menu_payload(
    *,
    title: str,
    subtitle: str | None,
    body_lines: list[str] | None,
    buttons: list[MenuButton],
    source: str,
    per_row: int = 3,
) -> dict[str, Any]:
    """A card that is mostly buttons: welcome menus, pickers, quick actions."""
    children: list[dict[str, Any]] = []
    if body_lines:
        children.append(
            {
                "type": "group",
                "direction": "column",
                "gap": 8,
                "children": [
                    {"type": "text", "value": line, "style": "body"}
                    for line in body_lines
                ],
            }
        )
    children.extend(_button_rows(buttons, source, per_row=per_row))

    section: dict[str, Any] = {"type": "section", "title": title, "children": children}
    if subtitle:
        section["subtitle"] = subtitle
    return {"root": section}


def build_chip_payload(
    *,
    title: str,
    subtitle: str | None,
    body_lines: list[str] | None,
    chips: list[MenuButton],
    source: str,
    footer_buttons: list[MenuButton] | None = None,
    per_row: int = 3,
    footnote: str | None = None,
) -> dict[str, Any]:
    """A dense grid of small buttons — one per record, label only.

    Distinct from `build_list_payload`, which gives every record a heading, a
    description, badges, and its own action button: correct for a handful of
    search results, unusably tall for a full roster. Here each record is just
    its name on a chip, so a long list stays scannable in one card and the
    detail card carries everything that was omitted.

    `footer_buttons` render below the grid, separated so set-wide actions don't
    read as another record.
    """
    children: list[dict[str, Any]] = []
    if body_lines:
        children.append(
            {
                "type": "group",
                "direction": "column",
                "gap": 8,
                "children": [
                    {"type": "text", "value": line, "style": "body"}
                    for line in body_lines
                ],
            }
        )

    children.extend(_button_rows(chips, source, per_row=per_row))

    if footer_buttons:
        children.append({"type": "divider"})
        # Footer buttons share the grid's width, so every button on the card
        # renders the same size. Packing them tighter than the chips above
        # made the secondary actions a visibly different shape.
        children.extend(_button_rows(footer_buttons, source, per_row=per_row))
    if footnote:
        children.append({"type": "text", "value": footnote, "style": "muted"})

    section: dict[str, Any] = {"type": "section", "title": title, "children": children}
    if subtitle:
        section["subtitle"] = subtitle
    return {"root": section}


def build_list_payload(
    items: list[CardItem],
    *,
    title: str,
    subtitle: str | None,
    id_field: str,
    source: str,
    footer_buttons: list[MenuButton] | None = None,
    footnote: str | None = None,
) -> dict[str, Any]:
    """Build the `card_payload` for a tappable list card.

    `footer_buttons` render below the list — follow-up actions on the result
    set as a whole ("Plan this day", "Try another vibe") rather than on one row.

    `footnote` renders last, in muted style: source pointers and caveats that
    must travel with the results but should not shout over them.
    """
    rendered: list[dict[str, Any]] = []

    for item in items:
        # Body and badges are omitted when empty rather than rendered blank,
        # so a list can be used purely for its left alignment: button labels
        # are centred by the client and cannot be aligned from here, so a bare
        # heading-plus-button row is the only way to line names up.
        column: list[dict[str, Any]] = [
            {"type": "heading", "value": item.heading, "level": 3},
        ]
        if item.body:
            column.append({"type": "text", "value": item.body, "style": "body"})
        column.extend(_badge(label, variant) for label, variant in item.badges)

        rendered.append(
            {
                "children": [
                    {"type": "group", "direction": "column", "gap": 8, "children": column},
                    {
                        "type": "button",
                        "label": item.button_label,
                        "primary": True,
                        "action": {
                            "selection": {id_field: item.record_id, "source": source}
                        },
                    },
                ]
            }
        )

    children: list[dict[str, Any]] = [{"type": "list", "items": rendered}]
    if footer_buttons:
        children.extend(_button_rows(footer_buttons, source))
    if footnote:
        children.append({"type": "divider"})
        children.append({"type": "text", "value": footnote, "style": "muted"})

    section: dict[str, Any] = {
        "type": "section",
        "title": title,
        "children": children,
    }
    if subtitle:
        section["subtitle"] = subtitle

    return {"root": section}


@dataclass
class DetailBlock:
    """A titled group of lines on a detail card, e.g. "How to join"."""

    title: str
    lines: list[str]


def build_detail_payload(
    *,
    title: str,
    heading: str,
    body: str,
    badges: list[tuple[str, str]],
    rows: list[DetailRow],
    blocks: list[DetailBlock] | None = None,
    footnote: str | None = None,
    back_label: str,
    back_action: str,
    source: str,
    extra_buttons: list[MenuButton] | None = None,
) -> dict[str, Any]:
    """Build the `card_payload` for a single-record detail card.

    `rows` are one-line facts (Category, Interests). `blocks` are short titled
    lists — how to join, what's similar — so everything a student needs sits on
    the card itself rather than in a paragraph above it.

    `extra_buttons` sit in the action row before Back — record-specific actions
    like "Directions to this event".
    """
    column: list[dict[str, Any]] = [_badge(label, variant) for label, variant in badges]
    column.append({"type": "heading", "value": heading, "level": 2})
    column.append({"type": "text", "value": body, "style": "body"})

    if rows:
        column.append({"type": "divider"})
        column.extend(
            {"type": "text", "value": f"{row.label}: {row.value}", "style": "body"}
            for row in rows
        )

    for block in blocks or []:
        column.append({"type": "divider"})
        # Level 3 deliberately: the element-tree renderer only accepts the
        # levels the reference implementation uses, and a level it does not
        # know makes the whole card fail to render rather than degrading.
        column.append({"type": "heading", "value": block.title, "level": 3})
        column.extend(
            {"type": "text", "value": line, "style": "body"} for line in block.lines
        )

    if footnote:
        column.append({"type": "divider"})
        column.append({"type": "text", "value": footnote, "style": "muted"})

    action_row: list[dict[str, Any]] = [
        _button(button, source) for button in (extra_buttons or [])
    ]
    action_row.append(
        {
            "type": "button",
            "label": back_label,
            "primary": False,
            "action": {"selection": {"action": back_action, "source": source}},
        }
    )

    section: dict[str, Any] = {
        "type": "section",
        "title": title,
        "children": [
            {"type": "group", "direction": "column", "gap": 12, "children": column},
            {"type": "group", "direction": "row", "gap": 8, "children": action_row},
        ],
    }
    return {"root": section}


def card_metadata(card_payload: dict[str, Any]) -> MetadataContent:
    """Wrap a payload dict in the MetadataContent block ChatMessage carries."""
    return MetadataContent(
        type="metadata",
        metadata={
            "card_protocol_version": CARD_PROTOCOL_VERSION,
            "requires_card_interaction": "true",
            "card_kind": "custom",
            "card_payload": json.dumps(card_payload),
        },
    )


def menu_message(
    preamble: str,
    *,
    title: str,
    subtitle: str | None,
    body_lines: list[str] | None,
    buttons: list[MenuButton],
    source: str,
    per_row: int = 3,
) -> ChatMessage:
    """A text bubble plus a button-menu card. The zero-typing entry point."""
    payload = build_menu_payload(
        title=title,
        subtitle=subtitle,
        body_lines=body_lines,
        buttons=buttons,
        source=source,
        per_row=per_row,
    )
    return card_message(preamble, payload)


def card_message(preamble: str, payload: dict[str, Any]) -> ChatMessage:
    """A ChatMessage carrying a card, with a text bubble when there is one.

    An empty `preamble` sends the card alone rather than an empty TextContent,
    which would render as a stray blank bubble. That matters for runs of cards
    sent together, where only the first says anything.

    No EndSessionContent: the session has to stay open for the user to tap a
    card and get a reply.
    """
    content: list[Any] = []
    if preamble.strip():
        content.append(TextContent(type="text", text=preamble))
    content.append(card_metadata(payload))
    return ChatMessage(timestamp=utc_now(), msg_id=uuid4(), content=content)
