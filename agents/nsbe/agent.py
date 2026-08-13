"""UCSC NSBE chapter agent.

Answers questions about the UC Santa Cruz chapter of the National Society of
Black Engineers, from what the chapter publishes on its own pages.

The first of the per-club agents, and a different shape from the three
Welcome Week agents: it speaks for one organization rather than searching many.
That changes what honesty requires. The clubs agent stores no contact or
meeting details for anyone, because for most organizations it would be
guessing; this chapter publishes both, so they are stated with a citation and a
read date. What the chapter has not published — officers, event dates, dues —
is answered with "ask them", never filled in.

Runs locally and reaches ASI:One through an Agentverse mailbox.
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
from agents_shared.guard import EchoGuard, is_assistant_prose, is_stale_replay
from agents_shared.loader import nsbe
from agents_shared.registration import register
from agents_shared.transport import agent_kwargs, deliver

load_dotenv()

AGENT_NAME = "ucsc_nsbe"
DISPLAY_NAME = "UCSC NSBE"
PORT = int(os.getenv("NSBE_PORT", "8024"))
SEED = os.getenv("NSBE_SEED_PHRASE", "ucsc-nsbe-change-me")

# Agentverse caps AgentProfile.description at 300 characters.
DESCRIPTION = (
    "The UC Santa Cruz chapter of the National Society of Black Engineers. "
    "When and where they meet, what the chapter is, how to join, and how to "
    "reach them - taken from the chapter's own published pages, with the date "
    "each was read."
)

README = """# UCSC NSBE 🛠️

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:chatprotocol](https://img.shields.io/badge/chatprotocol-3D8BD3)
![tag:ucsc](https://img.shields.io/badge/ucsc-3D8BD3)
![tag:nsbe](https://img.shields.io/badge/nsbe-3D8BD3)
![tag:engineering](https://img.shields.io/badge/engineering-3D8BD3)
![tag:cards](https://img.shields.io/badge/cards-3D8BD3)

The **National Society of Black Engineers at UC Santa Cruz** — one agent for
one chapter.

> "to increase the number of culturally responsible Black engineers and
> scientists who excel academically, succeed professionally and positively
> impact the community."

NSBE provides resources, opportunities, and community for students in STEM.
The chapter welcomes students of all majors and ethnicities, with a particular
focus on supporting Black students in STEM.

## What it answers

- **📅 When they meet** — day, time, and room
- **🤝 How to join** — every route the chapter publishes
- **🎯 What NSBE is** — the chapter's own mission statement
- **🔗 Their links** — site, Instagram, LinkedIn, linktree, resume form,
  national NSBE

## Try asking

- *when do they meet*
- *how do I join*
- *what is NSBE*
- *what's their instagram*

## Honesty about the data

Everything here comes from pages the chapter publishes itself:

- [nsbe.engineering.ucsc.edu](https://nsbe.engineering.ucsc.edu/) — the
  chapter's page on UCSC's engineering subdomain
- [their linktree](https://linktr.ee/eventsComingUpUCSC) — the link hub that
  page points at

Both were read on **2026-08-12**, and the agent says so whenever it gives a
detail that could go out of date.

**Meeting times are the fact most likely to go stale** without a page
changing, so they are never given without that date and a pointer to
[Instagram](https://www.instagram.com/nsbe.ucsc/), where the chapter actually
announces changes.

**Officer names, event dates, and dues are deliberately absent** — the chapter
publishes none of them. Asked for any of those, the agent says it doesn't hold
them and points you at the chapter directly, rather than inventing an answer.

## Related agents

- **UCSC Clubs & Societies** — find organizations across campus
- **UCSC Welcome Week Events** — what's on during Slug Start
- **UCSC Campus Navigation** — walking directions
"""

agent = Agent(**agent_kwargs(name=AGENT_NAME, seed=SEED, port=PORT))
from agents.nsbe.protocols.chat_proto import chat_proto, guard  # noqa: E402,F401


@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"{DISPLAY_NAME} starting at {ctx.agent.address}")
    ctx.logger.info(f"Chapter data read {nsbe()['_meta']['sources']['chapter_site']['checked']}")
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
