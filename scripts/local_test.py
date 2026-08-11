"""In-process end-to-end test of all three agents.

Drives each agent's real chat handler with synthetic ChatMessages and asserts on
what comes back. No Agentverse, no mailbox, no network, no open ports.

Handlers are pulled from the protocol's registry rather than the module
namespace, because that registry holds the actual async functions the uAgents
runtime dispatches to — so this exercises the same code path as production.

    make e2e
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# This is an offline gate: force the deterministic parsers regardless of what
# is configured in .env, so runs are reproducible and make no network calls.
# Popping the env var is not enough — every agent module calls load_dotenv()
# at import and would put the key straight back — so stub the client module.
os.environ.pop("ASI_ONE_API_KEY", None)

# Isolate the shared profile store too, so E2E runs don't leave state behind.
import tempfile as _tempfile

os.environ["UCSC_PROFILE_PATH"] = os.path.join(_tempfile.mkdtemp(), "profiles.json")

from common import asi1 as _asi1

_asi1.is_enabled = lambda: False  # type: ignore[assignment]

from uagents import Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    MetadataContent,
    StartSessionContent,
    TextContent,
)

USER = "agent1qtestuser000000000000000000000000000000000000000000000000000"

failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)


# --- fakes --------------------------------------------------------------------


class FakeLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def _record(self, level: str, message: Any) -> None:
        self.lines.append(f"{level}: {message}")

    def info(self, message: Any) -> None:
        self._record("info", message)

    def debug(self, message: Any) -> None:
        self._record("debug", message)

    def warning(self, message: Any) -> None:
        self._record("warning", message)

    def error(self, message: Any) -> None:
        self._record("error", message)

    def exception(self, message: Any) -> None:
        self._record("exception", message)


class FakeStorage:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


class FakeAgentHandle:
    name = "test-agent"
    address = "agent1qtestagent00000000000000000000000000000000000000000000000"


class FakeContext:
    """Enough of uagents.Context for the chat handlers to run."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.storage = FakeStorage()
        self.agent = FakeAgentHandle()
        self.session = uuid4()
        self.sent: list[tuple[str, Any]] = []

    async def send(self, destination: str, message: Any) -> None:
        self.sent.append((destination, message))

    @property
    def replies(self) -> list[Any]:
        return [message for _, message in self.sent]


# --- helpers ------------------------------------------------------------------


def handler_for(protocol: Protocol, model_name: str):
    """Resolve a protocol's registered async handler by message model name."""
    for digest, model in protocol._models.items():
        if model.__name__ == model_name:
            return protocol._signed_message_handlers[digest]
    raise LookupError(f"no handler registered for {model_name}")


def reset_guards() -> None:
    """Clear every agent's echo guard.

    The guards are module-level singletons — correct for a long-running agent,
    but it means one test's queries would otherwise be suppressed as duplicates
    when the next test repeats them.
    """
    for module_name in (
        "agents.navigation.agent",
        "agents.events.agent",
        "agents.clubs.agent",
    ):
        module = __import__(module_name, fromlist=["guard"])
        module.guard.reset()


def user_message(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


def session_start() -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[StartSessionContent(type="start-session")],
    )


def text_of(message: ChatMessage) -> str:
    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def card_payload(message: ChatMessage) -> dict | None:
    for item in message.content:
        if isinstance(item, MetadataContent):
            return json.loads(item.metadata["card_payload"])
    return None


async def converse(protocol: Protocol, messages: list[ChatMessage]) -> FakeContext:
    """Run a sequence of inbound messages against one agent, sharing context."""
    handle = handler_for(protocol, "ChatMessage")
    ctx = FakeContext()
    for message in messages:
        await handle(ctx, USER, message)
    return ctx


def assert_ack_first(ctx: FakeContext, label: str, inbound_count: int) -> None:
    acks = [m for m in ctx.replies if isinstance(m, ChatAcknowledgement)]
    check(
        len(acks) == inbound_count,
        f"{label}: expected {inbound_count} acknowledgements, got {len(acks)}",
    )
    check(
        bool(ctx.replies) and isinstance(ctx.replies[0], ChatAcknowledgement),
        f"{label}: first thing sent must be an acknowledgement, before any work",
    )


def chat_replies(ctx: FakeContext) -> list[ChatMessage]:
    return [m for m in ctx.replies if isinstance(m, ChatMessage)]


# --- navigation ---------------------------------------------------------------


async def test_navigation() -> None:
    from agents.navigation.agent import chat_proto

    ctx = await converse(
        chat_proto,
        [session_start(), user_message("from Cowell to Science Hill")],
    )
    assert_ack_first(ctx, "navigation", inbound_count=2)

    replies = chat_replies(ctx)
    check(len(replies) == 2, f"navigation: expected welcome + answer, got {len(replies)}")

    welcome = text_of(replies[0])
    check("Campus Navigation" in welcome, "navigation: welcome does not identify itself")
    check(
        "Events" in welcome and "Clubs" in welcome,
        "navigation: welcome does not cross-reference the sibling agents",
    )

    answer = replies[1]
    body = text_of(answer)
    check("Science Hill" in body, "navigation: answer omits the destination")
    check("min" in body, "navigation: answer omits a duration")
    check("estimate" in body.lower(), "navigation: duration not marked an estimate")
    check("Effort:" in body, "navigation: route omits the effort meter")
    # The session stays open: route cards carry reroute buttons ("gentler",
    # "step-free", "after dark") and a closed session would kill them.
    check(
        not any(isinstance(i, EndSessionContent) for i in answer.content),
        "navigation: a route reply must keep the session open for reroute taps",
    )
    payload = card_payload(answer)
    check(payload is not None, "navigation: route reply carries no card")
    if payload is not None:
        check(
            "reroute" in json.dumps(payload),
            "navigation: route card has no reroute buttons",
        )


async def test_navigation_echo_loop() -> None:
    """Feeding the agent its own reply must not produce another reply."""
    from agents.navigation.agent import chat_proto

    handle = handler_for(chat_proto, "ChatMessage")
    ctx = FakeContext()

    await handle(ctx, USER, user_message("from Cowell to Science Hill"))
    first = chat_replies(ctx)
    check(len(first) == 1, "navigation echo: expected one reply to the first query")

    echoed = text_of(first[0])
    await handle(ctx, USER, user_message(echoed))

    check(
        len(chat_replies(ctx)) == 1,
        "navigation echo: agent replied to its own echoed output — loop risk",
    )
    check(
        any("Suppressed" in line for line in ctx.logger.lines),
        "navigation echo: suppression was not logged",
    )


async def test_navigation_duplicate_suppressed() -> None:
    from agents.navigation.agent import chat_proto

    handle = handler_for(chat_proto, "ChatMessage")
    ctx = FakeContext()
    message = "where is Quarry Plaza"

    await handle(ctx, USER, user_message(message))
    await handle(ctx, USER, user_message(message))

    check(
        len(chat_replies(ctx)) == 1,
        "navigation: identical repeated query should be suppressed",
    )


# --- events -------------------------------------------------------------------


async def test_events() -> None:
    from agents.events.agent import chat_proto

    ctx = await converse(
        chat_proto,
        [session_start(), user_message("what's happening Wednesday")],
    )
    assert_ack_first(ctx, "events", inbound_count=2)

    replies = chat_replies(ctx)
    check(len(replies) == 2, f"events: expected welcome + listing, got {len(replies)}")

    listing = replies[1]
    body = text_of(listing)
    check("Wednesday" in body, "events: listing omits the requested day")
    # Events themselves render on the card, so their times are checked there.
    check(
        "time not yet published" in json.dumps(card_payload(listing)),
        "events: unpublished times not stated as unpublished",
    )
    check(
        "welcome.ucsc.edu" in json.dumps(card_payload(listing)),
        "events: listing omits the official source link",
    )

    payload = card_payload(listing)
    check(payload is not None, "events: listing carries no card")
    if payload:
        root = payload["root"]
        check(root["type"] == "section", "events: card root is not a section")
        items = root["children"][0]["items"]
        check(bool(items), "events: card has no items")
        button = items[0]["children"][-1]
        check(
            button["type"] == "button"
            and "event_id" in button["action"]["selection"],
            "events: card item has no tappable event_id action",
        )

    check(
        not any(isinstance(i, EndSessionContent) for i in listing.content),
        "events: a card message must keep the session open for taps",
    )


async def test_events_card_tap() -> None:
    from agents.events.agent import chat_proto

    handle = handler_for(chat_proto, "ChatMessage")
    ctx = FakeContext()

    await handle(ctx, USER, user_message("what's happening Tuesday"))
    payload = card_payload(chat_replies(ctx)[0])
    assert payload is not None
    first_id = payload["root"]["children"][0]["items"][0]["children"][-1]["action"][
        "selection"
    ]["event_id"]

    tap = json.dumps({"event_id": first_id, "source": "events_tab"})
    await handle(ctx, USER, user_message(tap))

    replies = chat_replies(ctx)
    check(len(replies) == 2, f"events tap: expected a detail reply, got {len(replies)}")
    detail = text_of(replies[1])
    check("Where:" in detail, "events tap: detail omits the location")
    check("Time:" in detail, "events tap: detail omits the time line")

    # Tapping the same card again must still work — taps bypass the echo guard.
    await handle(ctx, USER, user_message(tap))
    check(
        len(chat_replies(ctx)) == 3,
        "events tap: repeating a tap was wrongly suppressed as a duplicate",
    )


async def test_events_back_button() -> None:
    from agents.events.agent import chat_proto

    handle = handler_for(chat_proto, "ChatMessage")
    ctx = FakeContext()

    await handle(ctx, USER, user_message("what's happening Tuesday"))
    await handle(
        ctx,
        USER,
        user_message(json.dumps({"action": "back_to_events", "source": "events_tab"})),
    )

    replies = chat_replies(ctx)
    check(len(replies) == 2, "events back: no reply to the back action")
    check(
        card_payload(replies[1]) is not None,
        "events back: should return to a card listing",
    )


# --- clubs --------------------------------------------------------------------


async def test_clubs() -> None:
    from agents.clubs.agent import chat_proto

    ctx = await converse(
        chat_proto, [session_start(), user_message("clubs about hiking")]
    )
    assert_ack_first(ctx, "clubs", inbound_count=2)

    replies = chat_replies(ctx)
    check(len(replies) == 2, f"clubs: expected welcome + listing, got {len(replies)}")

    listing = replies[1]
    body = text_of(listing)
    # Organizations render on the card, so the match is verified there.
    check(
        "Hiking" in json.dumps(card_payload(listing)),
        "clubs: listing omits the obvious match",
    )
    check(
        "not a live roster" in json.dumps(card_payload(listing)),
        "clubs: listing omits the representative-examples caveat",
    )
    check(
        "getinvolved.ucsc.edu" in json.dumps(card_payload(listing)),
        "clubs: listing omits the official directory link",
    )

    payload = card_payload(listing)
    check(payload is not None, "clubs: listing carries no card")
    if payload:
        items = payload["root"]["children"][0]["items"]
        button = items[0]["children"][-1]
        check(
            "club_id" in button["action"]["selection"],
            "clubs: card item has no tappable club_id action",
        )


async def test_clubs_card_tap() -> None:
    from agents.clubs.agent import chat_proto

    handle = handler_for(chat_proto, "ChatMessage")
    ctx = FakeContext()

    await handle(ctx, USER, user_message("I'm into anime"))
    payload = card_payload(chat_replies(ctx)[0])
    assert payload is not None
    club_id = payload["root"]["children"][0]["items"][0]["children"][-1]["action"][
        "selection"
    ]["club_id"]

    await handle(
        ctx, USER, user_message(json.dumps({"club_id": club_id, "source": "clubs_tab"}))
    )

    replies = chat_replies(ctx)
    check(len(replies) == 2, "clubs tap: no detail reply")
    detail = text_of(replies[1])
    check("soar@ucsc.edu" in detail, "clubs tap: detail omits the official contact")
    check(
        "not a live roster entry" in detail,
        "clubs tap: detail omits the not-a-roster caveat",
    )


# --- acknowledgement handler --------------------------------------------------


async def test_ack_handler_is_registered() -> None:
    """A missing ack handler leaves the published manifest incomplete."""
    for module_name in (
        "agents.navigation.agent",
        "agents.events.agent",
        "agents.clubs.agent",
    ):
        module = __import__(module_name, fromlist=["chat_proto"])
        try:
            handle = handler_for(module.chat_proto, "ChatAcknowledgement")
        except LookupError:
            check(False, f"{module_name}: no ChatAcknowledgement handler registered")
            continue

        ctx = FakeContext()
        await handle(
            ctx,
            USER,
            ChatAcknowledgement(
                timestamp=datetime.now(timezone.utc), acknowledged_msg_id=uuid4()
            ),
        )
        check(
            ctx.sent == [],
            f"{module_name}: acknowledgement handler should not send anything",
        )


# --- runner -------------------------------------------------------------------


async def main() -> int:
    tests = [
        ("navigation: route query", test_navigation),
        ("navigation: echo loop defence", test_navigation_echo_loop),
        ("navigation: duplicate suppression", test_navigation_duplicate_suppressed),
        ("events: day listing + card", test_events),
        ("events: card tap", test_events_card_tap),
        ("events: back button", test_events_back_button),
        ("clubs: interest listing + card", test_clubs),
        ("clubs: card tap", test_clubs_card_tap),
        ("all: acknowledgement handler", test_ack_handler_is_registered),
    ]

    for label, test in tests:
        before = len(failures)
        reset_guards()
        try:
            await test()
        except Exception as exc:  # a raised error is a failed test, not a crash
            failures.append(f"{label}: raised {type(exc).__name__}: {exc}")
        status = "ok" if len(failures) == before else "FAIL"
        print(f"  [{status}] {label}")

    print(f"\nIn-process E2E: {checks} assertions across 3 agents.")
    if failures:
        print(f"\nFAILED ({len(failures)}):\n")
        for failure in failures:
            print(f"  ✗ {failure}")
        return 1

    print("All clear — ack-first ordering, card payloads, taps, and echo defences all hold.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
