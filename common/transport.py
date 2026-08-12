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
