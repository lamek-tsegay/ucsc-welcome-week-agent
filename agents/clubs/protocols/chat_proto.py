"""Chat protocol for the clubs agent.

Responsibilities, in the order the handler runs them: ACK first, welcome on
session start, drop replayed history, re-orient on menu asks, decode card
taps (taps bypass the echo guard - tapping twice is legitimate), drop relayed
assistant prose and echoes, then hand real queries to the service layer.
Every outbound goes through `deliver`, which retries failed sends.
"""

from __future__ import annotations

import json
import os

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

from agents.clubs import cards
from agents.clubs.cards import BACK_ACTION, CLUB_ID_FIELD
from agents.clubs.search import by_id as club_by_id
from agents.clubs.service import (
    WELCOME,
    bridge_to_navigation,
    respond_to_category,
    respond_to_query,
    respond_to_selection,
    respond_to_vibe,
)
from agents_shared.chat import (
    create_text_chat,
    is_menu_request,
    make_ack,
    parse_card_selection,
    strip_mention,
)
from agents_shared.chat_flow import (
    accept_text,
    note_outbound,
    reject_after_selection,
    send_noted,
)
from agents_shared.guard import EchoGuard
from agents_shared.registration import register
from agents_shared.transport import agent_kwargs, deliver

load_dotenv()


LAST_QUERY_KEY = "clubs:last_query"
SHOWN_IDS_KEY = "clubs:shown_ids"

chat_proto = Protocol(spec=chat_protocol_spec)
guard = EchoGuard()


def _note_outbound(sender: str, message: ChatMessage) -> None:
    note_outbound(guard, sender, message)


async def _send_query_result(ctx: Context, sender: str, text: str) -> None:
    message, shown_ids = await respond_to_query(text)
    ctx.storage.set(LAST_QUERY_KEY, text)
    ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
    _note_outbound(sender, message)
    await deliver(ctx, sender, message)


async def _send(ctx: Context, sender: str, message: ChatMessage) -> None:
    _note_outbound(sender, message)
    await deliver(ctx, sender, message)


async def _handle_selection(
    ctx: Context, sender: str, selection: dict[str, str]
) -> bool:
    """Act on a card tap. Returns False to fall through to text handling."""
    action = selection.get("action", "")

    if action == BACK_ACTION:
        previous = ctx.storage.get(LAST_QUERY_KEY) or "show me a spread"
        await _send_query_result(ctx, sender, previous)
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

    if action == "category":
        result = respond_to_category(selection.get("category", ""))
        if result is None:
            return False
        message, shown_ids = result
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    # A client that honours the button's url opens it and never sends these.
    # One that ignores it sends the tap, and the student gets the address as
    # text rather than a button that did nothing.
    if action in {"open_site", "open_directory", "open_email",
                  "open_club_link", "open_club_email"}:
        await _send(ctx, sender, cards.link_fallback_message(action, selection))
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

    club_id = selection.get(CLUB_ID_FIELD)
    if club_id and not action:
        message = respond_to_selection(club_id)
        await _send(ctx, sender, message)
        return True

    return False


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await deliver(ctx, sender, make_ack(msg))

    if any(isinstance(item, StartSessionContent) for item in msg.content):
        await _send(ctx, sender, cards.welcome_message())
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
            await _send(ctx, sender, cards.welcome_message())
            return

        # Card taps bypass the guard — tapping twice is legitimate, not an echo.
        selection = parse_card_selection(
            text, id_field=CLUB_ID_FIELD, extra_fields=cards.EXTRA_FIELDS
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

        # A navigation-shaped question typed here should just get answered.
        bridged = await bridge_to_navigation(text)
        if bridged:
            answer = create_text_chat(bridged)
            _note_outbound(sender, answer)
            await deliver(ctx, sender, answer)
            return

        ctx.logger.info(f"Clubs query from {sender}: {text!r}")
        try:
            await _send_query_result(ctx, sender, text)
        except Exception:
            ctx.logger.exception("Clubs query failed")
            fallback = (
                "Something went wrong searching. Try an interest — *hiking*, "
                "*music*, *tech* — or ask *what categories are there*."
            )
            guard.note_outbound(sender, fallback)
            await deliver(ctx, sender, create_text_chat(fallback))
        return


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"Ack from {sender} for {msg.acknowledged_msg_id}")


