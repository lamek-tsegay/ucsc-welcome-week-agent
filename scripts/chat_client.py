"""Drive the three live agents over real HTTP as a real uAgent.

This is a heavier test than `scripts/local_test.py`. That one calls handlers
in-process with a fake context. This one is an actual uAgent that sends signed
envelopes over HTTP to the three agents running as separate processes, and
receives their replies through its own chat protocol handler. It exercises
envelope signing, transport, protocol dispatch, and session handling — everything
except the Agentverse mailbox hop and ASI:One itself.

No API keys and no Agentverse account required.

Run the three agents in local-endpoint mode first, then this:

    UCSC_LOCAL_ENDPOINT=1 make nav      # terminal 1
    UCSC_LOCAL_ENDPOINT=1 make events   # terminal 2
    UCSC_LOCAL_ENDPOINT=1 make clubs    # terminal 3
    python -m scripts.chat_client       # terminal 4

Or use `make live`, which orchestrates all four.

Target addresses are derived from the same seeds the agents use, so nothing is
hardcoded and the two sides cannot disagree.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents.resolver import RulesBasedResolver
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.identity import Identity

load_dotenv()

CLIENT_PORT = int(os.getenv("CLIENT_PORT", "8030"))
CLIENT_SEED = os.getenv("CLIENT_SEED_PHRASE", "ucsc-welcome-week-test-client")

# Wait this long after the last reply before declaring the run finished.
QUIET_PERIOD_SECONDS = float(os.getenv("CLIENT_QUIET_SECONDS", "6"))
HARD_DEADLINE_SECONDS = float(os.getenv("CLIENT_DEADLINE_SECONDS", "90"))


@dataclass
class Target:
    label: str
    seed_env: str
    seed_default: str
    port_env: str
    port_default: int
    queries: list[str]
    tap_id_field: str | None = None

    @property
    def seed(self) -> str:
        return os.getenv(self.seed_env, self.seed_default)

    @property
    def port(self) -> int:
        return int(os.getenv(self.port_env, str(self.port_default)))

    @property
    def address(self) -> str:
        return Identity.from_seed(self.seed, 0).address

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}/submit"


TARGETS = [
    Target(
        label="navigation",
        seed_env="NAVIGATION_SEED_PHRASE",
        seed_default="ucsc-welcome-week-navigation-change-me",
        port_env="NAVIGATION_PORT",
        port_default=8021,
        queries=[
            "how do I get from Porter to McHenry Library",
            "route from Cowell to Science Hill avoiding hills",
            "where is Quarry Plaza",
            "what's near Crown College",
        ],
    ),
    Target(
        label="events",
        seed_env="EVENTS_SEED_PHRASE",
        seed_default="ucsc-welcome-week-events-change-me",
        port_env="EVENTS_PORT",
        port_default=8022,
        queries=[
            "what's happening Wednesday",
            "any events for Crown students",
        ],
        tap_id_field="event_id",
    ),
    Target(
        label="clubs",
        seed_env="CLUBS_SEED_PHRASE",
        seed_default="ucsc-welcome-week-clubs-change-me",
        port_env="CLUBS_PORT",
        port_default=8023,
        queries=[
            "clubs about hiking",
            "I'm into anime",
        ],
        tap_id_field="club_id",
    ),
]

BY_ADDRESS = {target.address: target for target in TARGETS}

client = Agent(
    name="ucsc_test_client",
    seed=CLIENT_SEED,
    port=CLIENT_PORT,
    endpoint=[f"http://127.0.0.1:{CLIENT_PORT}/submit"],
    # Point straight at the agents on localhost instead of resolving via Almanac,
    # so this works offline and without any registration.
    resolve=RulesBasedResolver(
        {target.address: target.endpoint for target in TARGETS}
    ),
)

chat_proto = Protocol(spec=chat_protocol_spec)


@dataclass
class Stats:
    sent: int = 0
    acks: int = 0
    replies: int = 0
    cards: int = 0
    taps_sent: int = 0
    tapped: set[str] = field(default_factory=set)
    per_agent: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


stats = Stats()


def text_chat(text: str) -> ChatMessage:
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


def first_card_record_id(msg: ChatMessage, id_field: str) -> str | None:
    """Pull the first tappable record id out of a card payload."""
    for item in msg.content:
        if not isinstance(item, MetadataContent):
            continue
        payload = json.loads(item.metadata["card_payload"])
        children = payload.get("root", {}).get("children", [])
        if not children or children[0].get("type") != "list":
            continue
        for entry in children[0].get("items", []):
            for node in entry.get("children", []):
                selection = node.get("action", {}).get("selection", {})
                if id_field in selection:
                    return selection[id_field]
    return None


def _quit(status: int) -> None:
    """Exit from inside an interval handler without asyncio teardown noise.

    sys.exit inside a uAgents interval task surfaces as an unretrieved task
    exception; this test script has nothing to clean up, so leave directly.
    """
    sys.stdout.flush()
    os._exit(status)


def summarise(text: str, limit: int = 240) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + " …"


@client.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"Test client at {ctx.agent.address}")
    print("\n" + "=" * 78)
    print("DRIVING LIVE AGENTS OVER HTTP")
    print("=" * 78)
    for target in TARGETS:
        print(f"  {target.label:<11} {target.address}")
        print(f"  {'':<11} {target.endpoint}")

    for target in TARGETS:
        await ctx.send(target.address, session_start())
        stats.sent += 1
        for query in target.queries:
            await ctx.send(target.address, text_chat(query))
            stats.sent += 1


@chat_proto.on_message(ChatMessage)
async def on_reply(ctx: Context, sender: str, msg: ChatMessage):
    target = BY_ADDRESS.get(sender)
    label = target.label if target else sender[:16]

    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id
    ))

    stats.replies += 1
    stats.per_agent[label] = stats.per_agent.get(label, 0) + 1

    body = "\n".join(i.text for i in msg.content if isinstance(i, TextContent))
    has_card = any(isinstance(i, MetadataContent) for i in msg.content)
    if has_card:
        stats.cards += 1

    print(f"\n--- reply from {label}{'  [+card]' if has_card else ''} ---")
    print(summarise(body))

    # Tap the first *record* card each agent sends, once, to exercise the
    # selection path. Cards without record rows are fine — welcome menus and
    # pickers are button-only by design — so keep watching until a listing
    # arrives; the end-of-run check catches an agent that never produces one.
    if has_card and target and target.tap_id_field and label not in stats.tapped:
        record_id = first_card_record_id(msg, target.tap_id_field)
        if record_id:
            stats.tapped.add(label)
            stats.taps_sent += 1
            print(f"    ↳ tapping {target.tap_id_field}={record_id}")
            await ctx.send(
                sender,
                text_chat(
                    json.dumps(
                        {
                            target.tap_id_field: record_id,
                            "source": f"{label}_tab",
                        }
                    )
                ),
            )
            stats.sent += 1


@chat_proto.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    stats.acks += 1


@client.on_interval(period=2.0)
async def finish(ctx: Context):
    """End the run once replies stop arriving, or at the hard deadline."""
    elapsed = getattr(finish, "_elapsed", 0.0) + 2.0
    finish._elapsed = elapsed
    last_count = getattr(finish, "_last_count", -1)

    if stats.replies != last_count:
        finish._last_count = stats.replies
        finish._quiet = 0.0
        return

    quiet = getattr(finish, "_quiet", 0.0) + 2.0
    finish._quiet = quiet

    if quiet < QUIET_PERIOD_SECONDS and elapsed < HARD_DEADLINE_SECONDS:
        return

    print("\n" + "=" * 78)
    print("RESULT")
    print("=" * 78)
    print(f"  messages sent        {stats.sent}")
    print(f"  acknowledgements     {stats.acks}")
    print(f"  replies received     {stats.replies}")
    print(f"  card messages        {stats.cards}")
    print(f"  card taps sent       {stats.taps_sent}")
    print(f"  replies per agent    {stats.per_agent}")

    problems = list(stats.problems)
    silent = [t.label for t in TARGETS if t.label not in stats.per_agent]
    if silent:
        problems.append(f"no reply at all from: {', '.join(silent)}")
    if stats.acks == 0:
        problems.append("no acknowledgements received — ack path may be broken")
    for target in TARGETS:
        if target.tap_id_field and target.label not in stats.tapped:
            problems.append(f"{target.label}: never produced a tappable card")

    if problems:
        print("\n  PROBLEMS:")
        for problem in problems:
            print(f"    ✗ {problem}")
        print()
        _quit(1)

    print("\n  All three agents answered over HTTP, acknowledged, and served cards.")
    print()
    _quit(0)


client.include(chat_proto, publish_manifest=False)


if __name__ == "__main__":
    client.run()
