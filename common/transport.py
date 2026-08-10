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
    base: dict[str, Any] = {"name": name, "seed": seed, "port": port}

    if local_endpoint_mode():
        base["endpoint"] = [f"http://127.0.0.1:{port}/submit"]
    else:
        base["mailbox"] = True

    return base
