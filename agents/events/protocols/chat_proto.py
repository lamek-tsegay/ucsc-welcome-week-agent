"""Chat protocol for the events agent.

Responsibilities, in the order the handler runs them: ACK first, welcome on
session start, drop replayed history, re-orient on menu asks, decode card
taps (taps bypass the echo guard - tapping twice is legitimate), drop relayed
assistant prose and echoes, then hand real queries to the service layer.
Every outbound goes through `deliver`, which retries failed sends.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    MetadataContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from agents.events import cards
from agents.events.cards import BACK_ACTION, EVENT_ID_FIELD
from agents.events.service import (
    WELCOME,
    respond_to_plan,
    respond_to_query,
    respond_to_selection,
    respond_to_vibe,
)
from agents.events.recommend import by_id as event_by_id, detect_college
from agents_shared import profile
from agents_shared.chat import (
    create_text_chat,
    is_menu_request,
    make_ack,
    parse_card_selection,
    strip_mention,
)
from agents_shared.colleges import by_key, parse_home_declaration
from agents_shared.chat_flow import (
    accept_text,
    note_outbound,
    reject_after_selection,
    send_noted,
)
from agents_shared.guard import EchoGuard
from agents_shared.loader import events_window
from agents_shared.registration import register
from agents_shared.transport import agent_kwargs, deliver

load_dotenv()

# "i'm hungry", "food rn", "starving" — answer with food events AND where to
# actually eat right now (dining halls), because Welcome Week events aren't a
# meal plan.
_HUNGRY_RE = re.compile(
    r"\b(i'?m\s+hungry|hungry\b|starving|food\s+rn|need\s+food|where.*\beat\b)",
    re.IGNORECASE,
)


LAST_QUERY_KEY = "events:last_query"
SHOWN_IDS_KEY = "events:shown_ids"

chat_proto = Protocol(spec=chat_protocol_spec)
guard = EchoGuard()


def _today() -> date:
    """Reference date for relative queries.

    Overridable so the agent can be demonstrated as though it were Welcome Week
    without changing the machine clock.
    """
    override = os.getenv("UCSC_TODAY_OVERRIDE")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            pass
    return date.today()


async def _send_query_result(ctx: Context, sender: str, text: str) -> None:
    message, shown_ids = await respond_to_query(text, today=_today())
    ctx.storage.set(LAST_QUERY_KEY, text)
    ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
    _note_outbound(sender, message)
    await deliver(ctx, sender, message)


def _note_outbound(sender: str, message: ChatMessage) -> None:
    note_outbound(guard, sender, message)


async def _send(ctx: Context, sender: str, message: ChatMessage) -> None:
    await send_noted(guard, ctx, sender, message)


async def _handle_selection(
    ctx: Context, sender: str, selection: dict[str, str]
) -> bool:
    """Act on a card tap. Returns False to fall through to text handling."""
    action = selection.get("action", "")
    event_id = selection.get(EVENT_ID_FIELD)
    saved_college = profile.college(sender)

    if action == BACK_ACTION:
        previous = ctx.storage.get(LAST_QUERY_KEY) or "the whole week"
        await _send_query_result(ctx, sender, previous)
        return True

    if action == "set_college":
        college = by_key(selection.get("college"))
        if not college:
            return False
        profile.set_college(sender, college.name)
        await _send_query_result(
            ctx, sender, f"any events for {college.name} students"
        )
        return True

    if action == "my_college":
        if saved_college:
            await _send_query_result(
                ctx, sender, f"any events for {saved_college} students"
            )
        else:
            await _send(ctx, sender, cards.college_picker_message())
        return True

    if action == "quiz":
        await _send(ctx, sender, cards.vibe_picker_message())
        return True

    if action == "vibe_pick":
        result = respond_to_vibe(selection.get("vibe", ""))
        if result is None:
            return False
        message, shown_ids = result
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    if action == "plan_day":
        iso = selection.get("date", "")
        valid = {day["date"] for day in events_window()["days"]}
        if iso in valid:
            message, shown_ids = await respond_to_plan(iso)
            ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
            await _send(ctx, sender, message)
        else:
            await _send(ctx, sender, cards.day_picker_message())
        return True

    if action == "open_schedule":
        await _send(
            ctx,
            sender,
            create_text_chat(
                "The official Slug Start schedule — tap to open:\n"
                + cards.OFFICIAL_EVENTS_URL
            ),
        )
        return True

    if action == "about":
        await _send(ctx, sender, cards.about_message())
        return True

    if action == "links":
        await _send(ctx, sender, cards.links_message())
        return True

    if action == "quick":
        canned = selection.get("q", "").strip()
        if not canned:
            return False
        await _send_query_result(ctx, sender, canned)
        return True

    if event_id and not action:
        message = respond_to_selection(event_id)
        await _send(ctx, sender, message)
        return True

    return False


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await deliver(ctx, sender, make_ack(msg))

    if any(isinstance(item, StartSessionContent) for item in msg.content):
        message = cards.welcome_message(profile.college(sender))
        await _send(ctx, sender, message)
        return

    if any(isinstance(item, EndSessionContent) for item in msg.content):
        ctx.logger.info(f"Session ended by {sender}")
        return

    for item in msg.content:
        if isinstance(item, MetadataContent):
            ctx.logger.debug(f"Metadata from {sender}: {item.metadata}")
            continue
        if not isinstance(item, TextContent):
            continue

        # Replay handling lives in agents_shared.chat_flow.accept_text.
        text = await accept_text(guard, ctx, sender, item.text)
        if text is None:
            continue

        # "help" / "menu" / a bare greeting always re-orients — never a dead end.
        if is_menu_request(text):
            await _send(ctx, sender, cards.welcome_message(profile.college(sender)))
            return

        # Card taps must bypass the guard: tapping the same card twice is a
        # legitimate user action, not an echo.
        selection = parse_card_selection(
            text, id_field=EVENT_ID_FIELD, extra_fields=cards.EXTRA_FIELDS
        )
        if selection:
            ctx.logger.info(f"Card selection from {sender}: {selection}")
            try:
                if await _handle_selection(ctx, sender, selection):
                    return
            except Exception:
                ctx.logger.exception("Card action failed")

        # Prose/echo suppression lives in chat_flow.reject_after_selection.
        if reject_after_selection(guard, ctx, sender, text):
            return

        # "I'm at Crown" — remember the college, then show what's on for it.
        declared = parse_home_declaration(text)
        if declared:
            college_name = detect_college(declared)
            if college_name:
                profile.set_college(sender, college_name)
                await _send(
                    ctx,
                    sender,
                    create_text_chat(
                        f"Got it — you're at **{college_name}**. 🎓 I'll "
                        "filter events for your college. Here's what's on:"
                    ),
                )
                await _send_query_result(
                    ctx, sender, f"any events for {college_name} students"
                )
                return

        if _HUNGRY_RE.search(text):
            from agents_shared.links import dining_link_line

            await _send(
                ctx,
                sender,
                create_text_chat(
                    "Hungry? Two answers: 🍕\n\n"
                    f"**Right now:** the dining halls — {dining_link_line()}\n\n"
                    "**This week:** here's everything with food on the schedule:"
                ),
            )
            await _send_query_result(ctx, sender, "free food this week")
            return

        ctx.logger.info(f"Events query from {sender}: {text!r}")
        try:
            await _send_query_result(ctx, sender, text)
        except Exception:
            ctx.logger.exception("Events query failed")
            fallback = (
                "Something went wrong looking that up. Try a day — "
                "*what's happening Wednesday* — or *show me the whole week*."
            )
            guard.note_outbound(sender, fallback)
            await deliver(ctx, sender, create_text_chat(fallback))
        return


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"Ack from {sender} for {msg.acknowledged_msg_id}")


