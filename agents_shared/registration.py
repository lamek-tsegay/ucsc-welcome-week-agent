"""Agentverse registration, shared by all three agents.

`register_chat_agent` publishes the agent's name, description, and README to
Agentverse. That README is not decoration: it is the metadata ASI:One's router
matches against user intent, so it doubles as the agent's discovery surface.

Registration is best-effort. An agent that cannot register still runs and still
answers anyone who knows its address — it just won't be discoverable.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from uagents import Agent, Context
from uagents_core.utils.registration import (
    RegistrationRequestCredentials,
    register_chat_agent,
)

load_dotenv()


def agentverse_key() -> str | None:
    return os.getenv("AGENTVERSE_API_KEY") or None


def _endpoint_for(agent: Agent, port: int) -> str:
    """Best-effort endpoint URL for registration."""
    endpoints = getattr(agent, "_endpoints", None)
    if endpoints:
        return endpoints[0].url
    return f"http://localhost:{port}"


async def register(
    ctx: Context,
    agent: Agent,
    *,
    display_name: str,
    description: str,
    readme: str,
    seed: str,
    port: int,
) -> None:
    """Register with Agentverse, logging clearly on both paths."""
    key = agentverse_key()
    if not key:
        ctx.logger.warning(
            "AGENTVERSE_API_KEY not set — skipping registration. The agent runs, "
            "but ASI:One cannot discover it."
        )
        return

    try:
        register_chat_agent(
            display_name,
            _endpoint_for(agent, port),
            active=True,
            credentials=RegistrationRequestCredentials(
                agentverse_api_key=key,
                agent_seed_phrase=seed,
            ),
            readme=readme,
            description=description,
        )
    except Exception:
        ctx.logger.exception("Agentverse registration failed")
        return

    ctx.logger.info(f"Registered '{display_name}' with Agentverse")
