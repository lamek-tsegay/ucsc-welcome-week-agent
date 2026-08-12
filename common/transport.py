"""How each agent is reachable.

`mailbox=True` and `endpoint=[...]` are mutually exclusive on a uAgent — setting
both silently breaks chat delivery. This module keeps that choice in one place
so all three agents cannot drift apart on it.

Default is mailbox: the agent polls Agentverse for inbound messages, needing no
public IP or tunnel, which is what makes ASI:One reachable from a laptop.

Setting `UCSC_LOCAL_ENDPOINT=1` switches to a plain localhost endpoint instead.
That makes the agent directly addressable over HTTP on this machine, so it can be
driven by a local client agent without any Agentverse account or API key — see
`scripts/chat_client.py`. It is a testing mode, not a deployment mode: a
127.0.0.1 endpoint is not reachable from ASI:One.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any


def local_endpoint_mode() -> bool:
    return bool(os.getenv("UCSC_LOCAL_ENDPOINT"))


def agent_kwargs(*, name: str, seed: str, port: int) -> dict[str, Any]:
    """Constructor kwargs for an Agent, honouring the transport mode."""
    base: dict[str, Any] = {
        "name": name,
        "seed": seed,
        "port": port,
        # Required by the replay defence in common/guard.py, which holds a
        # message it has already answered to see whether a newer one is right
        # behind it. uagents handles messages one at a time by default, so a
        # held message would block the very message it is waiting for: it would
        # wait the full hold, conclude it was newest, and answer anyway — while
        # every other replayed message queued behind it did the same. Handling
        # concurrently lets the holds overlap, which is what makes the check
        # mean anything. A test pins this on.
        "handle_messages_concurrently": True,
    }

    if local_endpoint_mode():
        base["endpoint"] = [f"http://127.0.0.1:{port}/submit"]
    else:
        base["mailbox"] = True

    return base


async def deliver(ctx: Any, destination: str, message: Any, *, attempts: int = 3,
                  base_delay: float = 0.6) -> Any:
    """Send a message, retrying when the relay drops it.

    Nothing in uagents retries a failed send: the dispenser logs one ERROR and
    the message is gone. The live log on 2026-08-12 showed what that costs —
    a card tap answered in milliseconds, then

        Failed to deliver message to <sender>
        @ ['https://agentverse.ai/v2/agents/proxy/submit']: ['500: Internal Server Error']

    and the student watched ASI:One spin on "working on your request" for an
    answer that had been thrown away in transit. Delivery is the only leg of
    that round trip this side can do anything about, so a FAILED status gets
    two more tries with a pause for a transient relay fault to clear.

    Test doubles' send() returns None; only an explicit FAILED status retries.
    """
    from uagents_core.types import DeliveryStatus

    delay = base_delay
    status = None
    for attempt in range(attempts):
        status = await ctx.send(destination, message)
        if getattr(status, "status", None) != DeliveryStatus.FAILED:
            return status
        if attempt + 1 < attempts:
            ctx.logger.warning(
                f"Delivery to {destination[:16]}… failed "
                f"({getattr(status, 'detail', '')!r}); retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
            delay *= 2.5
    ctx.logger.error(
        f"Delivery to {destination[:16]}… failed after {attempts} attempts — "
        "the reply is lost and the client will show no answer for this turn"
    )
    return status
