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
    respond_to_full_roster,
    respond_to_query,
    respond_to_selection,
    respond_to_vibe,
)
from common.chat import (
    create_text_chat,
    is_menu_request,
    make_ack,
    parse_card_selection,
    strip_mention,
)
from common.guard import EchoGuard
from common.registration import register
from common.transport import agent_kwargs

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

README = """# UCSC Clubs & Societies 🎓

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
chat_proto = Protocol(spec=chat_protocol_spec)
guard = EchoGuard()


def _note_outbound(sender: str, message: ChatMessage) -> None:
    for item in message.content:
        if isinstance(item, TextContent):
            guard.note_outbound(sender, item.text)


async def _send_query_result(ctx: Context, sender: str, text: str) -> None:
    message, shown_ids = await respond_to_query(text)
    ctx.storage.set(LAST_QUERY_KEY, text)
    ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
    _note_outbound(sender, message)
    await ctx.send(sender, message)


async def _send(ctx: Context, sender: str, message: ChatMessage) -> None:
    _note_outbound(sender, message)
    await ctx.send(sender, message)


async def _handle_selection(
    ctx: Context, sender: str, selection: dict[str, str]
) -> bool:
    """Act on a card tap. Returns False to fall through to text handling."""
    action = selection.get("action", "")

    if action == BACK_ACTION:
        previous = ctx.storage.get(LAST_QUERY_KEY) or "show me a spread"
        await _send_query_result(ctx, sender, previous)
        return True

    if action == "quiz":
        await _send(ctx, sender, cards.vibe_picker_message())
        return True

    if action == "show_all":
        message, shown_ids = respond_to_full_roster()
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    if action == "vibe_pick":
        result = respond_to_vibe(selection.get("vibe", ""))
        if result is None:
            return False
        message, shown_ids = result
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    if action == "category":
        result = respond_to_category(selection.get("category", ""))
        if result is None:
            return False
        message, shown_ids = result
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    if action == "about":
        await _send(ctx, sender, cards.about_message())
        return True

    if action == "links":
        await _send(ctx, sender, cards.links_message())
        return True

    if action == "quick":
        canned = selection.get("q", "").strip()
        if not canned:
            return False
        await _send_query_result(ctx, sender, canned)
        return True

    club_id = selection.get(CLUB_ID_FIELD)
    if club_id and not action:
        message = respond_to_selection(club_id)
        await _send(ctx, sender, message)
        return True

    return False


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, make_ack(msg))

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

        text = strip_mention(item.text or "")
        if not text:
            continue

        # "help" / "menu" / a bare greeting always re-orients — never a dead end.
        if is_menu_request(text):
            await _send(ctx, sender, cards.welcome_message())
            return

        # Card taps bypass the guard — tapping twice is legitimate, not an echo.
        selection = parse_card_selection(
            text, id_field=CLUB_ID_FIELD, extra_fields=cards.EXTRA_FIELDS
        )
        if selection:
            ctx.logger.info(f"Card selection from {sender}: {selection}")
            try:
                if await _handle_selection(ctx, sender, selection):
                    return
            except Exception:
                ctx.logger.exception("Card action failed")

        reason = guard.classify(sender, text)
        if reason is not None:
            ctx.logger.info(f"Suppressed inbound from {sender} ({reason})")
            return
        guard.should_handle(sender, text)

        # A navigation-shaped question typed here should just get answered.
        bridged = await bridge_to_navigation(text)
        if bridged:
            answer = create_text_chat(bridged)
            _note_outbound(sender, answer)
            await ctx.send(sender, answer)
            return

        ctx.logger.info(f"Clubs query from {sender}: {text!r}")
        try:
            await _send_query_result(ctx, sender, text)
        except Exception:
            ctx.logger.exception("Clubs query failed")
            fallback = (
                "Something went wrong searching. Try an interest — *hiking*, "
                "*music*, *tech* — or ask *what categories are there*."
            )
            guard.note_outbound(sender, fallback)
            await ctx.send(sender, create_text_chat(fallback))
        return


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.debug(f"Ack from {sender} for {msg.acknowledged_msg_id}")


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
