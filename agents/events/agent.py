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
    respond_to_my_plan,
    respond_to_plan,
    respond_to_query,
    respond_to_selection,
    respond_to_vibe,
)
from agents.events.recommend import by_id as event_by_id, detect_college
from common import profile
from common.chat import (
    create_text_chat,
    is_menu_request,
    make_ack,
    parse_card_selection,
    strip_mention,
)
from common.colleges import by_key, parse_home_declaration
from common.guard import EchoGuard, is_stale_replay
from common.loader import events_window
from common.registration import register
from common.transport import agent_kwargs

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

- **🎯 Interest matcher** - one tap, zero typing: pick what you're in the mood
  for (free food, meeting people, outdoors, arts, career, off campus) and see
  what fits across the whole week. Built for students who don't know what's on.
- **Day lookup** - what's on Monday, Wednesday, Saturday, or the whole week
- **Day planner** - *plan my Tuesday* lays out that day, confirmed events first
- **⭐ My plan** - star events and get your own Welcome Week list back
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
- *plan my Tuesday*
- *I'm at Crown* — then see events for your college
- *free food this week*
- *outdoor stuff on Saturday*
- *show me the whole week*

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
chat_proto = Protocol(spec=chat_protocol_spec)
guard = EchoGuard()


def _today() -> date:
    """Reference date for relative queries.

    Overridable so the agent can be demonstrated as though it were Welcome Week
    without changing the machine clock.
    """
    override = os.getenv("UCSC_TODAY_OVERRIDE")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            pass
    return date.today()


async def _send_query_result(ctx: Context, sender: str, text: str) -> None:
    message, shown_ids = await respond_to_query(text, today=_today())
    ctx.storage.set(LAST_QUERY_KEY, text)
    ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
    _note_outbound(sender, message)
    await ctx.send(sender, message)


def _note_outbound(sender: str, message: ChatMessage) -> None:
    for item in message.content:
        if isinstance(item, TextContent):
            guard.note_outbound(sender, item.text)


async def _send(ctx: Context, sender: str, message: ChatMessage) -> None:
    _note_outbound(sender, message)
    await ctx.send(sender, message)


async def _handle_selection(
    ctx: Context, sender: str, selection: dict[str, str]
) -> bool:
    """Act on a card tap. Returns False to fall through to text handling."""
    action = selection.get("action", "")
    event_id = selection.get(EVENT_ID_FIELD)
    saved_college = profile.college(sender)

    if action == BACK_ACTION:
        previous = ctx.storage.get(LAST_QUERY_KEY) or "the whole week"
        await _send_query_result(ctx, sender, previous)
        return True

    if action == "set_college":
        college = by_key(selection.get("college"))
        if not college:
            return False
        profile.set_college(sender, college.name)
        await _send_query_result(
            ctx, sender, f"any events for {college.name} students"
        )
        return True

    if action == "my_college":
        if saved_college:
            await _send_query_result(
                ctx, sender, f"any events for {saved_college} students"
            )
        else:
            await _send(ctx, sender, cards.college_picker_message())
        return True

    if action == "quiz":
        await _send(ctx, sender, cards.vibe_picker_message())
        return True

    if action == "vibe_pick":
        result = respond_to_vibe(selection.get("vibe", ""))
        if result is None:
            return False
        message, shown_ids = result
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    if action == "plan_day":
        iso = selection.get("date", "")
        valid = {day["date"] for day in events_window()["days"]}
        if iso in valid:
            message, shown_ids = await respond_to_plan(iso)
            ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
            await _send(ctx, sender, message)
        else:
            await _send(ctx, sender, cards.day_picker_message())
        return True

    if action == "save_event" and event_id:
        event = event_by_id(event_id)
        if event is None:
            return False
        now_saved = profile.toggle_saved(sender, "plan", event_id)
        # A confirmation only — no card. The student is already looking at the
        # detail they tapped from.
        await _send(
            ctx,
            sender,
            cards.plan_toggled_message(
                event,
                saved=now_saved,
                total=len(profile.saved(sender, "plan")),
            ),
        )
        return True

    if action == "my_plan":
        message, shown_ids = await respond_to_my_plan(
            profile.saved(sender, "plan")
        )
        ctx.storage.set(SHOWN_IDS_KEY, json.dumps(shown_ids))
        await _send(ctx, sender, message)
        return True

    if action == "clear_plan":
        profile.clear_saved(sender, "plan")
        await _send(
            ctx,
            sender,
            create_text_chat(
                "Cleared. ⭐ Star any event to start a fresh plan."
            ),
        )
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

    if event_id and not action:
        message = respond_to_selection(
            event_id, saved=event_id in profile.saved(sender, "plan")
        )
        await _send(ctx, sender, message)
        return True

    return False


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, make_ack(msg))

    if any(isinstance(item, StartSessionContent) for item in msg.content):
        message = cards.welcome_message(profile.college(sender))
        await _send(ctx, sender, message)
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

        # ASI:One replays the conversation on every turn, so one tap arrives
        # with the original question and every earlier tap behind it. Drop the
        # ones already answered — see common/guard.is_stale_replay.
        sequence = guard.note_inbound(sender)
        if await is_stale_replay(guard, sender, text, sequence):
            ctx.logger.info(f"Dropped replayed message from {sender}: {text[:60]!r}")
            return
        guard.mark_answered(sender, text)

        # "help" / "menu" / a bare greeting always re-orients — never a dead end.
        if is_menu_request(text):
            await _send(ctx, sender, cards.welcome_message(profile.college(sender)))
            return

        # Card taps must bypass the guard: tapping the same card twice is a
        # legitimate user action, not an echo.
        selection = parse_card_selection(
            text, id_field=EVENT_ID_FIELD, extra_fields=cards.EXTRA_FIELDS
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

        # "I'm at Crown" — remember the college, then show what's on for it.
        declared = parse_home_declaration(text)
        if declared:
            college_name = detect_college(declared)
            if college_name:
                profile.set_college(sender, college_name)
                await _send(
                    ctx,
                    sender,
                    create_text_chat(
                        f"Got it — you're at **{college_name}**. 🎓 I'll "
                        "filter events for your college. Here's what's on:"
                    ),
                )
                await _send_query_result(
                    ctx, sender, f"any events for {college_name} students"
                )
                return

        if _HUNGRY_RE.search(text):
            from common.links import dining_link_line

            await _send(
                ctx,
                sender,
                create_text_chat(
                    "Hungry? Two answers: 🍕\n\n"
                    f"**Right now:** the dining halls — {dining_link_line()}\n\n"
                    "**This week:** here's everything with food on the schedule:"
                ),
            )
            await _send_query_result(ctx, sender, "free food this week")
            return

        ctx.logger.info(f"Events query from {sender}: {text!r}")
        try:
            await _send_query_result(ctx, sender, text)
        except Exception:
            ctx.logger.exception("Events query failed")
            fallback = (
                "Something went wrong looking that up. Try a day — "
                "*what's happening Wednesday* — or *show me the whole week*."
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
