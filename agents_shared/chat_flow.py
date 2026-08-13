"""The inbound-text pipeline every agent runs, in one place.

Four protocol modules used to carry identical copy-pasted stanzas of this.
The order is load-bearing and was earned live:

1. `accept_text` — strip the @mention, drop replayed history (ASI:One resends
   the whole conversation each turn), mark the survivor answered.
2. The agent parses card selections itself (taps bypass the echo guard —
   tapping twice is legitimate).
3. `reject_after_selection` — drop relayed assistant prose (the orchestrator's
   own words sent back as queries) and echoes of our own output.
"""

from __future__ import annotations

from uagents_core.contrib.protocols.chat import ChatMessage, TextContent

from agents_shared.chat import strip_mention
from agents_shared.guard import EchoGuard, is_assistant_prose, is_stale_replay
from agents_shared.transport import deliver


def note_outbound(guard: EchoGuard, sender: str, message: ChatMessage) -> None:
    """Remember what we said so the echo guard can recognise it coming back."""
    for item in message.content:
        if isinstance(item, TextContent):
            guard.note_outbound(sender, item.text)


async def send_noted(guard: EchoGuard, ctx, sender: str, message: ChatMessage) -> None:
    """The standard outbound: remember it, then deliver with retries."""
    note_outbound(guard, sender, message)
    await deliver(ctx, sender, message)


async def accept_text(guard: EchoGuard, ctx, sender: str, raw: str) -> str | None:
    """Strip, replay-drop, and mark answered. None means drop this item."""
    text = strip_mention(raw or "")
    if not text:
        return None

    sequence = guard.note_inbound(sender)
    if await is_stale_replay(guard, sender, text, sequence):
        ctx.logger.info(f"Dropped replayed message from {sender}: {text[:60]!r}")
        return None
    guard.mark_answered(sender, text)
    return text


def reject_after_selection(guard: EchoGuard, ctx, sender: str, text: str) -> bool:
    """True when the text is a relayed assistant turn or an echo, not a person."""
    if is_assistant_prose(text):
        ctx.logger.info(f"Dropped relayed assistant prose from {sender}")
        return True

    reason = guard.classify(sender, text)
    if reason is not None:
        ctx.logger.info(f"Suppressed inbound from {sender} ({reason})")
        return True
    guard.should_handle(sender, text)
    return False
