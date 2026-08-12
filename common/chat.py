"""Chat protocol helpers shared by all three agents.

Modelled on innovation-lab-examples/news-card-agent/shared.py, generalised so
the card-selection parser is not hard-coded to one id field.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from uagents_core.contrib.protocols.chat import (
    AgentContent,
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
)


def utc_now() -> datetime:
    """Timezone-aware UTC now. Avoids the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


def create_text_chat(text: str, *, end_session: bool = False) -> ChatMessage:
    """Build a text-only ChatMessage, optionally closing the session."""
    content: list[AgentContent] = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=utc_now(), msg_id=uuid4(), content=content)


def make_ack(msg: ChatMessage) -> ChatAcknowledgement:
    """Build the acknowledgement for an inbound message.

    Send this before doing any work — ASI:One expects a prompt ack, and a slow
    handler that acks late looks like a dead agent.
    """
    return ChatAcknowledgement(timestamp=utc_now(), acknowledged_msg_id=msg.msg_id)


# A JSON object embedded in surrounding prose. Selections often arrive this way
# when ASI:One's planner relays a tap instead of passing the payload through
# verbatim. Non-greedy and single-level is enough: selection payloads are flat.
_EMBEDDED_JSON_RE = re.compile(r"\{[^{}]*\}")

# Bare action words recognised in prose form. Only tokens that cannot occur in
# ordinary English ("directions" or "quiz" would false-positive on real
# questions, so those actions are recognised in JSON form only).
_PROSE_ACTION_RE = re.compile(
    r"\b(back_to_\w+|set_college|set_home|route_to|reroute|plan_day"
    r"|my_college|nearby_home|vibe_pick)\b",
    re.IGNORECASE,
)


# ASI:One prepends the agent's mention handle to relayed messages —
# "@ucsc-clubs Hi tell me what clubs there are" arrives with the handle inside
# the text. Observed in live traffic on 2026-08-09; strip it before any parsing
# or the handle pollutes keyword matching and landmark resolution.
_MENTION_RE = re.compile(r"^\s*(?:@[\w.-]+[,:]?\s+)+")


def strip_mention(text: str) -> str:
    """Remove leading @agent-handle mention(s) from inbound chat text."""
    return _MENTION_RE.sub("", text or "").strip()


# A student who is lost types one of these. Always answer with the welcome
# menu — a dead end here loses them for good.
_MENU_RE = re.compile(
    r"^\s*(help|menu|options|start\s*over|home|hi|hey|hello|what\s+can\s+you\s+do)"
    r"\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def is_menu_request(text: str) -> bool:
    """True for "help", "menu", a bare greeting — anything meaning "orient me"."""
    return bool(_MENU_RE.match(text or ""))


def parse_card_selection(
    text: str, *, id_field: str, extra_fields: tuple[str, ...] = ()
) -> dict[str, str] | None:
    """Extract a card-tap selection from inbound text.

    Card taps do not arrive as structured data. The chat UI delivers them either
    as a JSON object serialised into a text bubble (sometimes embedded in
    prose), or — when routed through ASI:One's planner — as prose that mentions
    the selection fields. All three shapes have to be handled.

    `id_field` is the record-id key this agent's cards emit, e.g. "event_id".
    `extra_fields` are additional selection keys this agent's buttons carry,
    e.g. ("college", "mode"). Returns a dict with whichever were found, or None.
    """
    if not text:
        return None

    stripped = text.strip()
    wanted = (id_field, "action", "source", *extra_fields)

    def from_json(candidate: str) -> dict[str, str] | None:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        found = {
            key: value
            for key in wanted
            if isinstance((value := data.get(key)), str)
        }
        return found or None

    if stripped.startswith("{") and stripped.endswith("}"):
        parsed = from_json(stripped)
        if parsed:
            return parsed

    # JSON blob inside prose: try each balanced-looking object.
    for match in _EMBEDDED_JSON_RE.finditer(stripped):
        parsed = from_json(match.group(0))
        # Require more than a stray {"source": ...} to count as a selection.
        if parsed and set(parsed) - {"source"}:
            return parsed

    selection: dict[str, str] = {}

    # Prose form: "the user picked event_id ph_farm_tour from events_tab".
    # The boundary matters: "college" must not match inside "set_college".
    for key in (id_field, *extra_fields):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(key)}[\s:=\"']*([A-Za-z0-9_\-]+)",
            re.IGNORECASE,
        )
        match = pattern.search(stripped)
        if match:
            selection[key] = match.group(1)

    action_match = _PROSE_ACTION_RE.search(stripped)
    if action_match:
        selection["action"] = action_match.group(1).lower()

    return selection or None
