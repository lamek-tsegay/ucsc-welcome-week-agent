"""Chat protocol for the NSBE chapter agent.

Responsibilities, in the order the handler runs them: ACK first, welcome on
session start, drop replayed history, re-orient on menu asks, decode card
taps (taps bypass the echo guard - tapping twice is legitimate), drop relayed
assistant prose and echoes, then hand real queries to the service layer.
Every outbound goes through `deliver`, which retries failed sends.
"""

from __future__ import annotations

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

from agents.nsbe import cards
from agents.nsbe.service import respond_to_query, respond_to_topic
from agents_shared.chat import (
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
from agents_shared.loader import nsbe
from agents_shared.registration import register
from agents_shared.transport import agent_kwargs, deliver

load_dotenv()


chat_proto = Protocol(spec=chat_protocol_spec)
guard = EchoGuard()


def _note_outbound(sender: str, message: ChatMessage) -> None:
    note_outbound(guard, sender, message)


async def _send(ctx: Context, sender: str, message: ChatMessage) -> None:
    await send_noted(guard, ctx, sender, message)


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
            text, id_field="topic", extra_fields=cards.EXTRA_FIELDS
        )
        # A client that honours the button's url opens it and never sends
        # this; one that ignores it gets the address as text instead of a
        # button that did nothing.
        if selection and selection.get("action") == "open_link":
            await _send(ctx, sender, cards.link_fallback_message(selection.get("link", "")))
            return
        if selection and selection.get("topic"):
            ctx.logger.info(f"Card selection from {sender}: {selection}")
            try:
                await _send(ctx, sender, respond_to_topic(selection["topic"]))
                return
            except Exception:
                ctx.logger.exception("Card action failed")

        # Prose/echo suppression lives in chat_flow.reject_after_selection.
        if reject_after_selection(guard, ctx, sender, text):
            return

        ctx.logger.info(f"NSBE query from {sender}: {text!r}")
        try:
            await _send(ctx, sender, respond_to_query(text))
        except Exception:
            ctx.logger.exception("NSBE query failed")
            await _send(ctx, sender, cards.unknown_message())
        return


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"Ack from {sender} for {msg.acknowledged_msg_id}")


