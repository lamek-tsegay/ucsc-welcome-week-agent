"""UCSC Clubs & Societies agent.

Helps new students find student organizations by interest or category during
Slug Start / Fall Welcome Week (Sept 21-26 2026), rendered as tappable ASI:One
cards.

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
from agents_shared.guard import EchoGuard, is_assistant_prose, is_stale_replay
from agents_shared.registration import register
from agents_shared.transport import agent_kwargs, deliver

load_dotenv()

AGENT_NAME = "ucsc_clubs_societies"
DISPLAY_NAME = "UCSC Clubs & Societies"
PORT = int(os.getenv("CLUBS_PORT", "8023"))
SEED = os.getenv("CLUBS_SEED_PHRASE", "ucsc-welcome-week-clubs-change-me")

LAST_QUERY_KEY = "clubs:last_query"
SHOWN_IDS_KEY = "clubs:shown_ids"

# Agentverse caps AgentProfile.description at 300 characters and rejects the
# whole registration if it is longer — see tests/test_data_integrity.py.
DESCRIPTION = (
    "Helps new UC Santa Cruz students find student organizations, clubs, and "
    "societies by interest or category during Slug Start / Fall Welcome Week "
    "(Sept 21-26). Includes all 35 Baskin Engineering orgs from the official "
    "directory, plus examples across cultural, arts, sports, and more."
)

README = """# UCSC Clubs & Societies 🐌

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:chatprotocol](https://img.shields.io/badge/chatprotocol-3D8BD3)
![tag:ucsc](https://img.shields.io/badge/ucsc-3D8BD3)
![tag:clubs](https://img.shields.io/badge/clubs-3D8BD3)
![tag:welcomeweek](https://img.shields.io/badge/welcomeweek-3D8BD3)
![tag:cards](https://img.shields.io/badge/cards-3D8BD3)

Find student organizations at **UC Santa Cruz** during Slug Start / Fall Welcome
Week, **Monday Sept 21 - Saturday Sept 26**.

## What it does

- **🎯 Vibe matcher** - one tap, zero typing: pick a mood (creative, active,
  curious, chill, global, impact) and get matched across categories. Built for
  students who don't know any club names yet.
- **Interest matching** - describe what you're into in your own words and get
  matching organizations
- **Category browsing** - ten tappable categories from cultural and identity
  groups to hobby clubs
- **Name lookup** - find a specific organization
- **Interactive cards** - tap any organization for its category, interest tags,
  and how to actually join

## Try asking

- *Hi, I'd like to know about the clubs at UCSC* - I'll ask what you're into,
  then show you the organizations that fit
- tap **🎯 Match my vibe** and answer one question
- *clubs about hiking*
- *I'm into anime*
- *show me cultural orgs*
- *anything for pre-med students*
- *what categories are there*

## Categories

Cultural & Identity · Academic & Professional · Arts & Performance · Media &
Publications · Sports & Recreation · Service & Advocacy · Technology &
Engineering · Spiritual & Religious · Fraternity & Sorority Life · Games, Hobbies
& Special Interest

## Honesty about the data

Two tiers, clearly labelled:

- **Confirmed** — 35 engineering organizations listed on the official
  [Baskin Engineering student-organizations page](https://undergrad.engineering.ucsc.edu/student-organizations/)
  (checked 2026-08-09), each with the club link that page publishes. Confirmed
  means the organization exists - not its meeting times or current status.
- **Unofficial** — representative examples of the kinds of organizations UCSC
  has. The general Registered Student Organization directory is updated **weekly
  through fall** and cannot be confirmed from a static snapshot, so these are
  illustrations, not a roster.

Contact details and meeting times are **deliberately omitted rather than
guessed**, because a wrong email address sends you to the wrong place. For real
details:

- The official directory: [getinvolved.ucsc.edu](https://getinvolved.ucsc.edu/student-organizations/join/)
- Email SOAR: soar@ucsc.edu
- Go to **Cornucopia** (Tue Sept 22, East Upper Field), where most organizations
  table in person

## Related agents

- **UCSC Welcome Week Events** - what's happening and when
- **UCSC Campus Navigation** - directions to any venue
"""

agent = Agent(**agent_kwargs(name=AGENT_NAME, seed=SEED, port=PORT))
from agents.clubs.protocols.chat_proto import chat_proto, guard  # noqa: E402,F401


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
