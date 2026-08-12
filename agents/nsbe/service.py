"""Question routing for the NSBE chapter agent, independent of transport.

Deliberately keyword-only, with no LLM in the path. The chapter publishes a
small, fixed set of facts; the useful skill is recognising which one is being
asked for and saying "ask them" for everything else. A model would add latency
and the temptation to fill gaps that should stay visible.
"""

from __future__ import annotations

import re

from agents.nsbe import cards
from uagents_core.contrib.protocols.chat import ChatMessage

TOPICS = ("meetings", "join", "about", "links", "home")

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "meetings",
        re.compile(
            r"\b(meet(?:ing|ings|s)?|when|what\s+time|where|room|location|schedule"
            r"|tuesday|weekly)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "join",
        re.compile(
            r"\b(join|sign\s*up|signup|member|membership|get\s+involved|how\s+do\s+i"
            r"|dues|email\s+list|mailing\s+list|contact|reach)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "links",
        re.compile(
            r"\b(link|links|instagram|insta|ig|social|linkedin|website|site"
            r"|linktree|resume)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "about",
        re.compile(
            r"\b(what\s+is|who\s+are|about|mission|purpose|nsbe|national\s+society"
            r"|black\s+engineers|do\s+you\s+do|tell\s+me)\b",
            re.IGNORECASE,
        ),
    ),
]

# Questions the chapter has not published answers to. Matched before the
# general patterns so "who is the president" does not fall into "about".
_UNPUBLISHED_RE = re.compile(
    r"\b(president|officer|officers|board|e-?board|chair|treasurer|secretary"
    r"|who\s+runs|who\s+leads|next\s+event|upcoming\s+event|events?\s+(?:this|next)"
    r"|how\s+much|cost|fee|fees|price)\b",
    re.IGNORECASE,
)


def detect_topic(text: str) -> str | None:
    """Which published topic a question is asking about, or None."""
    if not text:
        return None
    if _UNPUBLISHED_RE.search(text):
        return None
    for topic, pattern in _PATTERNS:
        if pattern.search(text):
            return topic
    return None


def respond_to_topic(topic: str) -> ChatMessage:
    """The card for a topic. Falls back to the menu for anything unknown."""
    if topic == "meetings":
        return cards.meetings_message()
    if topic == "join":
        return cards.join_message()
    if topic == "about":
        return cards.about_message()
    if topic == "links":
        return cards.links_message()
    return cards.welcome_message()


def respond_to_query(text: str) -> ChatMessage:
    """Answer a typed question, or say plainly that it isn't published."""
    topic = detect_topic(text)
    if topic is None:
        return cards.unknown_message()
    return respond_to_topic(topic)
