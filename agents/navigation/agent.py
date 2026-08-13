"""UCSC Campus Navigation agent.

Answers walking-direction, location, and what's-nearby questions about the UC
Santa Cruz campus during Slug Start (Welcome Week), Sept 21–26 2026 — as
interactive cards: one-tap reroutes, tap-to-walk nearby lists, and a saved
home college so routes need no typed origin.

Runs locally and reaches ASI:One through an Agentverse mailbox.
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
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from agents.navigation import cards
from agents.navigation.service import (
    NavReply,
    events_pointer,
    reroute,
    respond,
    route_between,
)
import re

from agents_shared import profile
from agents_shared.chat import (
    create_text_chat,
    is_menu_request,
    make_ack,
    parse_card_selection,
    strip_mention,
)
from agents_shared.colleges import by_key, by_landmark
from agents_shared.guard import EchoGuard, is_assistant_prose, is_stale_replay
from agents_shared.loader import landmark_name, landmarks
from agents_shared.registration import register
from agents_shared.transport import agent_kwargs, deliver

# "always step-free", "step free on/off", "I use a wheelchair" — a persistent
# preference, distinct from asking for one step-free route.
_STEPFREE_ON_RE = re.compile(
    r"\b(always\s+step[\s-]?free|step[\s-]?free\s+(?:always|on)"
    r"|i\s+use\s+a\s+wheelchair|wheelchair\s+user)\b",
    re.IGNORECASE,
)
_STEPFREE_OFF_RE = re.compile(
    r"\bstep[\s-]?free\s+off\b", re.IGNORECASE
)

load_dotenv()

AGENT_NAME = "ucsc_campus_navigation"
DISPLAY_NAME = "UCSC Campus Navigation"
PORT = int(os.getenv("NAVIGATION_PORT", "8021"))
SEED = os.getenv("NAVIGATION_SEED_PHRASE", "ucsc-welcome-week-navigation-change-me")

DESCRIPTION = (
    "Walking directions, building locations, and what's-nearby answers for the UC "
    "Santa Cruz campus during Slug Start / Fall Welcome Week (Sept 21-26). Knows "
    "the ten residential colleges, remembers yours as a default starting point, "
    "routes around hills and stairs with one tap, and flags poorly lit paths."
)

README = """# UCSC Campus Navigation 🗺️

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:chatprotocol](https://img.shields.io/badge/chatprotocol-3D8BD3)
![tag:ucsc](https://img.shields.io/badge/ucsc-3D8BD3)
![tag:navigation](https://img.shields.io/badge/navigation-3D8BD3)
![tag:welcomeweek](https://img.shields.io/badge/welcomeweek-3D8BD3)
![tag:cards](https://img.shields.io/badge/cards-3D8BD3)

Campus navigation for **UC Santa Cruz** during Slug Start / Fall Welcome Week,
**Monday Sept 21 - Saturday Sept 26**.

UCSC is roughly 2,000 acres of forested hillside. Walking time here is driven by
elevation, not distance, so this agent routes with the hills in mind and will tell
you when the bus is the better answer.

## What it does

- **Walking directions** between campus landmarks, step by step, with climb and
  descent called out and an **effort meter** (▲▲▲▁▁) so you know what you're in for
- **One-tap reroutes** — every route card carries buttons: ⛰️ gentler,
  🪜 step-free, 🌙 after dark, 🔄 reverse. No retyping.
- **Remembers your college** — say *"I'm at Porter"* once (or tap it) and every
  route starts from there: *"route to the library"* just works
- **Tap-to-walk nearby lists** — ask *what's near Crown* and walk to any result
  with one tap
- **Night routing** that flags poorly lit forest paths
- **Bus alternatives** when the walk is a real climb

## Try asking

- *how do I get from Porter to McHenry Library*
- *I'm at Kresge* — then just *route to the bookstore*
- *route from Oakes to Science Hill avoiding hills*
- *what's near Crown College*
- *step-free route from Cowell to the Bay Tree Bookstore*

## Coverage

All ten residential colleges (Cowell, Stevenson, Crown, Merrill, Porter, Kresge,
Oakes, Rachel Carson, College Nine, John R. Lewis), McHenry and Science &
Engineering libraries, Science Hill, dining halls, OPERS and the athletics fields,
the Welcome Week venues including East Upper Field and the Quarry Amphitheater,
parking lots, campus entrances, and downtown / Boardwalk connections.

## Honesty about the data

Walking times and coordinates are **hand-curated estimates**, not official campus
survey data, and are presented as estimates. Bus routes are approximate and
unverified - check [scmtd.com](https://scmtd.com) for live schedules. Accessibility
flags are incomplete; confirm step-free routes with the Disability Resource Center.

## Related agents

- **UCSC Welcome Week Events** - what's happening and when
- **UCSC Clubs & Societies** - student organizations to join
"""

agent = Agent(**agent_kwargs(name=AGENT_NAME, seed=SEED, port=PORT))
from agents.navigation.protocols.chat_proto import chat_proto, guard  # noqa: E402,F401


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"{DISPLAY_NAME} starting at {ctx.agent.address}")
    await register(
        ctx,
        agent,
        display_name=DISPLAY_NAME,
        description=DESCRIPTION,
        readme=README,
        seed=SEED,
        port=PORT,
    )


agent.include(chat_proto, publish_manifest=True)


if __name__ == "__main__":
    agent.run()
