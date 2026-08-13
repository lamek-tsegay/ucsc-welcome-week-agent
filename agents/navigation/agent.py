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
chat_proto = Protocol(spec=chat_protocol_spec)
guard = EchoGuard()


# --- per-student memory -------------------------------------------------------


def _home_key(sender: str) -> str:
    return f"nav:home:{sender}"


def _route_key(sender: str) -> str:
    return f"nav:route:{sender}"


def _anchor_key(sender: str) -> str:
    return f"nav:anchor:{sender}"


def _home_id(ctx: Context, sender: str) -> str | None:
    """The student's starting point: nav-specific override, else profile.

    The profile college is shared with the other agents — telling the events
    agent "I'm at Crown" teaches this one too. A non-college landmark declared
    here ("I'm at McHenry") is nav-only, stored as a local override.
    """
    override = ctx.storage.get(_home_key(sender))
    if override:
        return override
    college_name = profile.college(sender)
    if college_name:
        from agents_shared.colleges import by_name

        college = by_name(college_name)
        if college:
            return college.landmark_id
    return None


def _remember(ctx: Context, sender: str, reply: NavReply) -> None:
    if reply.home_set:
        college = by_landmark(reply.home_set)
        if college:
            # A college home is shared knowledge; clear any nav-only override.
            profile.set_college(sender, college.name)
            ctx.storage.set(_home_key(sender), "")
        else:
            ctx.storage.set(_home_key(sender), reply.home_set)
    if reply.route_ctx is not None:
        ctx.storage.set(_route_key(sender), json.dumps(reply.route_ctx))
    if reply.anchor_id:
        ctx.storage.set(_anchor_key(sender), reply.anchor_id)


def _last_route(ctx: Context, sender: str) -> dict | None:
    raw = ctx.storage.get(_route_key(sender))
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _note_outbound(sender: str, message: ChatMessage) -> None:
    for item in message.content:
        if isinstance(item, TextContent):
            guard.note_outbound(sender, item.text)


async def _send(ctx: Context, sender: str, reply: NavReply) -> None:
    _remember(ctx, sender, reply)
    _note_outbound(sender, reply.message)
    await deliver(ctx, sender, reply.message)


async def _run_query(ctx: Context, sender: str, text: str) -> None:
    reply = await respond(
        text,
        home_id=_home_id(ctx, sender),
        last_route=_last_route(ctx, sender),
        always_accessible=profile.accessible(sender),
    )
    await _send(ctx, sender, reply)


# --- card action dispatch -----------------------------------------------------


async def _handle_selection(
    ctx: Context, sender: str, selection: dict[str, str]
) -> bool:
    """Act on a card tap. Returns False to fall through to text handling.

    Falling through matters: the prose-form parser can fire on ordinary
    sentences, and an unrecognised "selection" must still get a real answer.
    """
    action = selection.get("action", "")
    home_id = _home_id(ctx, sender)

    if action == "about":
        message = cards.about_message()
        _note_outbound(sender, message)
        await deliver(ctx, sender, message)
        return True

    if action == "links":
        message = cards.links_message()
        _note_outbound(sender, message)
        await deliver(ctx, sender, message)
        return True

    if action == "pref_stepfree":
        now_on = not profile.accessible(sender)
        profile.set_accessible(sender, now_on)
        message = cards.step_free_toggled_message(now_on)
        _note_outbound(sender, message)
        await deliver(ctx, sender, message)
        return True

    if action == "set_home":
        message = cards.college_picker_message()
        _note_outbound(sender, message)
        await deliver(ctx, sender, message)
        return True

    if action == "set_college":
        college = by_key(selection.get("college"))
        if not college:
            return False
        reply = await respond(f"I'm at {college.name}")
        await _send(ctx, sender, reply)
        return True

    if action == "nearby_home":
        if not home_id:
            message = cards.college_picker_message(
                note="I don't know your college yet."
            )
            _note_outbound(sender, message)
            await deliver(ctx, sender, message)
            return True
        await _run_query(ctx, sender, f"what's near {landmark_name(home_id)}")
        return True

    if action == "route_to":
        dest_id = selection.get("landmark_id", "")
        if dest_id not in landmarks():
            return False
        origin_id = ctx.storage.get(_anchor_key(sender)) or home_id
        if origin_id and origin_id != dest_id:
            reply = route_between(origin_id, dest_id)
            if reply:
                await _send(ctx, sender, reply)
                return True
        # No usable origin: ask, with the picker one tap away.
        await _run_query(ctx, sender, f"route to {landmark_name(dest_id)}")
        return True

    if action == "reroute":
        mode = selection.get("mode", "")
        last = _last_route(ctx, sender)
        if not last or mode not in {"hills", "stairs", "night", "reverse"}:
            return False
        reply = reroute(last, mode)
        if reply is None:
            return False
        await _send(ctx, sender, reply)
        return True

    if action == "quick":
        canned = selection.get("q", "").strip()
        if not canned:
            return False
        await _run_query(ctx, sender, canned)
        return True

    return False


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    # Acknowledge before doing any work.
    await deliver(ctx, sender, make_ack(msg))

    if any(isinstance(item, StartSessionContent) for item in msg.content):
        home_id = _home_id(ctx, sender)
        message = cards.welcome_message(
            landmark_name(home_id) if home_id else None,
            step_free=profile.accessible(sender),
        )
        _note_outbound(sender, message)
        await deliver(ctx, sender, message)
        return

    if any(isinstance(item, EndSessionContent) for item in msg.content):
        ctx.logger.info(f"Session ended by {sender}")
        return

    for item in msg.content:
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

        # "help" / "menu" / a bare greeting always re-orients, before anything
        # else can swallow it — a lost student must never hit a dead end.
        if is_menu_request(text):
            home_id = _home_id(ctx, sender)
            message = cards.welcome_message(
                landmark_name(home_id) if home_id else None,
                step_free=profile.accessible(sender),
            )
            _note_outbound(sender, message)
            await deliver(ctx, sender, message)
            return

        # Card taps bypass the guard — tapping twice is legitimate, not an echo.
        selection = parse_card_selection(
            text, id_field=cards.LANDMARK_FIELD, extra_fields=cards.EXTRA_FIELDS
        )
        if selection:
            ctx.logger.info(f"Card selection from {sender}: {selection}")
            try:
                if await _handle_selection(ctx, sender, selection):
                    return
            except Exception:
                ctx.logger.exception("Card action failed")

        # ASI:One's orchestrator sometimes sends its own generated prose in as
        # a query — its hand-off blurb, or a whole answer it wrote itself.
        # Answering it hands the orchestrator more text to fold in and re-send;
        # the observed end state is the UI stuck on "working on your request".
        # See common/guard.is_assistant_prose for the live-log evidence.
        if is_assistant_prose(text):
            ctx.logger.info(f"Dropped relayed assistant prose from {sender}")
            return

        reason = guard.classify(sender, text)
        if reason is not None:
            ctx.logger.info(f"Suppressed inbound from {sender} ({reason})")
            return
        guard.should_handle(sender, text)

        if _STEPFREE_ON_RE.search(text):
            profile.set_accessible(sender, True)
            message = cards.step_free_toggled_message(True)
            _note_outbound(sender, message)
            await deliver(ctx, sender, message)
            return
        if _STEPFREE_OFF_RE.search(text):
            profile.set_accessible(sender, False)
            message = cards.step_free_toggled_message(False)
            _note_outbound(sender, message)
            await deliver(ctx, sender, message)
            return

        bridge = events_pointer(text)
        if bridge:
            guard.note_outbound(sender, bridge)
            await deliver(ctx, sender, create_text_chat(bridge))
            return

        ctx.logger.info(f"Navigation query from {sender}: {text!r}")
        try:
            await _run_query(ctx, sender, text)
        except Exception:
            ctx.logger.exception("Navigation query failed")
            fallback = (
                "Something went wrong working that out. Try naming a start and an "
                "end, like *from Porter to McHenry Library*."
            )
            guard.note_outbound(sender, fallback)
            await deliver(ctx, sender, create_text_chat(fallback))
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
