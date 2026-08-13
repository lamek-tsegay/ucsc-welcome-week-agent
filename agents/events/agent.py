"""UCSC Welcome Week Events recommendation agent.

Recommends Slug Start / Fall Welcome Week events (Sept 21-26 2026) filtered by
day, residential college, and interest, and renders them as tappable ASI:One
cards.

Runs locally and reaches ASI:One through an Agentverse mailbox.
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
from agents_shared.guard import EchoGuard, is_assistant_prose, is_stale_replay
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

AGENT_NAME = "ucsc_welcome_week_events"
DISPLAY_NAME = "UCSC Welcome Week Events"
PORT = int(os.getenv("EVENTS_PORT", "8022"))
SEED = os.getenv("EVENTS_SEED_PHRASE", "ucsc-welcome-week-events-change-me")

LAST_QUERY_KEY = "events:last_query"
SHOWN_IDS_KEY = "events:shown_ids"

DESCRIPTION = (
    "What's on during UC Santa Cruz Slug Start / Fall Welcome Week (Monday Sept 21 "
    "to Saturday Sept 26). Ask what you're in the mood for, browse by day, filter "
    "by residential college, and star events into your own plan. Confirmed events "
    "are distinguished from examples, and event times are never invented."
)

README = """# UCSC Welcome Week Events 🎪

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:chatprotocol](https://img.shields.io/badge/chatprotocol-3D8BD3)
![tag:ucsc](https://img.shields.io/badge/ucsc-3D8BD3)
![tag:events](https://img.shields.io/badge/events-3D8BD3)
![tag:welcomeweek](https://img.shields.io/badge/welcomeweek-3D8BD3)
![tag:cards](https://img.shields.io/badge/cards-3D8BD3)

Event recommendations for **UC Santa Cruz Slug Start / Fall Welcome Week**,
**Monday Sept 21 - Saturday Sept 26**.

## What it does

Two ways in, and nothing else competing with them:

- **🎯 What are you into** - one tap, zero typing: pick what you're in the mood
  for (free food, meeting people, outdoors, arts, career, off campus) and see
  what fits across the whole week. Built for students who don't know what's on.
- **📅 Browse by day** - pick a day, see everything on it, confirmed first
- **Remembers your college** - say *I'm at Crown* once (or tap it); event
  recommendations use it from then on
- **College filtering** - programming for your residential college, since UCSC's
  first-day schedule depends on college affiliation
- **Interest matching** - food, music, sports, outdoors, career, cultural, tech,
  wellness, and more
- **Interactive cards** - tap any event for date, time, location, and who it's for
- **Relative dates** - "tonight" and "tomorrow" resolve against the Welcome Week
  window, and it tells you when you're asking outside it

## Try asking

- *Tell me about Welcome Week* - I'll ask what you're into, then show what fits
- *what's happening Wednesday*
- *I'm at Crown* — then see events for your college
- *free food this week*
- *outdoor stuff on Saturday*

## Confirmed events

These five have dates confirmed from the official UCSC page:

| Day | Event |
|---|---|
| Mon Sept 21 | New Admit Class Photo (East Upper Field) + Late Night at Athletics & Rec |
| Tue Sept 22 | Cornucopia festival (East Upper Field) |
| Wed Sept 23 | Student Employment & Work-Study Fair |
| Fri Sept 25 | Boardwalk Frolic (Santa Cruz Beach Boardwalk) |
| Sat Sept 26 | Choose Your Own Slugventure |

## Honesty about the data

The official page publishes **dates but not times**. Confirmed events therefore
show "time not yet published" rather than a guess. Other entries are
**placeholder examples** in this agent's seed data, labelled *Unofficial*
everywhere they appear. Your college sends its own first-day schedule separately
- check your email. Always confirm at
[the official Slug Start page](https://welcome.ucsc.edu/slug-life/fall-welcome-week/).

## Related agents

- **UCSC Campus Navigation** - walking directions to any venue. This agent
  covers what's on; routing is that agent's job.
- **UCSC Clubs & Societies** - student organizations to join
"""

agent = Agent(**agent_kwargs(name=AGENT_NAME, seed=SEED, port=PORT))
from agents.events.protocols.chat_proto import chat_proto, guard  # noqa: E402,F401


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
