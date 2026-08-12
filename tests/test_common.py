"""Shared infrastructure: echo guard, card builders, chat helpers, notices."""

from __future__ import annotations

import json

from common.cards import (
    CardItem,
    DetailRow,
    build_detail_payload,
    build_list_payload,
    card_message,
    card_metadata,
)
from common.chat import create_text_chat, parse_card_selection
from common.guard import EchoGuard, normalise
from common.notices import badge, event_time, marker
from uagents_core.contrib.protocols.chat import (
    EndSessionContent,
    MetadataContent,
    TextContent,
)


# --- echo guard ---------------------------------------------------------------


def test_first_message_is_handled():
    guard = EchoGuard()
    assert guard.should_handle("agent1x", "what's on Monday", now=0.0)


def test_duplicate_inside_window_is_suppressed():
    guard = EchoGuard(cooldown_seconds=0.0)
    assert guard.should_handle("agent1x", "what's on Monday", now=0.0)
    assert not guard.should_handle("agent1x", "what's on Monday", now=10.0)


def test_duplicate_after_window_is_allowed_again():
    guard = EchoGuard(dedup_window_seconds=60.0, cooldown_seconds=0.0)
    assert guard.should_handle("agent1x", "hello", now=0.0)
    assert guard.should_handle("agent1x", "hello", now=120.0)


def test_distinct_messages_pass():
    guard = EchoGuard(cooldown_seconds=0.0)
    assert guard.should_handle("agent1x", "what's on Monday", now=0.0)
    assert guard.should_handle("agent1x", "what's on Tuesday", now=1.0)


def test_cooldown_suppresses_rapid_fire():
    guard = EchoGuard(cooldown_seconds=5.0)
    assert guard.should_handle("agent1x", "first", now=0.0)
    assert not guard.should_handle("agent1x", "second", now=1.0)
    assert guard.should_handle("agent1x", "third", now=6.0)


def test_cooldown_is_per_sender():
    guard = EchoGuard(cooldown_seconds=5.0)
    assert guard.should_handle("agent1x", "hello", now=0.0)
    assert guard.should_handle("agent1y", "hello", now=0.5)


def test_our_own_reply_coming_back_is_detected_as_echo():
    guard = EchoGuard(cooldown_seconds=0.0)
    reply = "Porter College to McHenry Library is about 22 minutes on foot"
    guard.note_outbound("agent1x", reply, now=0.0)
    assert guard.classify("agent1x", reply, now=1.0) == "echo"
    assert not guard.should_handle("agent1x", reply, now=1.0)


def test_lightly_reworded_echo_is_still_detected():
    """ASI:One rewrites wording when it echoes, so matching must be fuzzy."""
    guard = EchoGuard(cooldown_seconds=0.0)
    guard.note_outbound("agent1x", "the walk from Porter to McHenry is 22 minutes", now=0.0)
    assert guard.classify(
        "agent1x", "The walk from Porter to McHenry is 22 minutes.", now=1.0
    ) == "echo"


def test_unrelated_text_is_not_an_echo():
    guard = EchoGuard(cooldown_seconds=0.0)
    guard.note_outbound("agent1x", "a long reply about walking routes", now=0.0)
    assert guard.classify("agent1x", "clubs about hiking", now=1.0) is None


def test_stale_outbound_memory_expires():
    guard = EchoGuard(cooldown_seconds=0.0, outbound_memory_seconds=10.0)
    guard.note_outbound("agent1x", "some reply text here", now=0.0)
    assert guard.classify("agent1x", "some reply text here", now=100.0) != "echo"


def test_empty_text_is_suppressed():
    guard = EchoGuard()
    assert not guard.should_handle("agent1x", "   ", now=0.0)
    assert guard.classify("agent1x", "", now=0.0) == "empty"


def test_several_distinct_questions_in_quick_succession_all_answered():
    """A person firing off different questions must not be silently dropped.

    Every suppression is invisible to the user, so an over-eager cooldown looks
    exactly like a broken agent. Only near-instant delivery is absorbed.
    """
    guard = EchoGuard()
    questions = [
        "how do I get from Porter to McHenry Library",
        "route from Cowell to Science Hill avoiding hills",
        "where is Quarry Plaza",
        "what's near Crown College",
    ]
    for index, question in enumerate(questions):
        moment = index * 0.5
        assert guard.should_handle("agent1x", question, now=moment), question


def test_instantaneous_double_delivery_is_absorbed():
    guard = EchoGuard()
    assert guard.should_handle("agent1x", "first question", now=0.0)
    assert not guard.should_handle("agent1x", "second question", now=0.05)


def test_burst_limit_stops_a_runaway_loop():
    """Last resort when a loop's wording varies too much for echo detection."""
    guard = EchoGuard(cooldown_seconds=0.0, max_burst=5, burst_window_seconds=10.0)
    for index in range(5):
        assert guard.should_handle("agent1x", f"distinct message {index}", now=index * 0.1)

    assert guard.classify("agent1x", "yet another one", now=0.6) == "flood"


def test_burst_limit_recovers_after_the_window():
    guard = EchoGuard(cooldown_seconds=0.0, max_burst=3, burst_window_seconds=10.0)
    for index in range(3):
        assert guard.should_handle("agent1x", f"message {index}", now=index * 0.1)
    assert not guard.should_handle("agent1x", "one too many", now=0.5)
    assert guard.should_handle("agent1x", "later message", now=20.0)


def test_burst_limit_is_per_sender():
    guard = EchoGuard(cooldown_seconds=0.0, max_burst=2, burst_window_seconds=10.0)
    assert guard.should_handle("agent1x", "a", now=0.0)
    assert guard.should_handle("agent1x", "b", now=0.1)
    assert not guard.should_handle("agent1x", "c", now=0.2)
    # A different sender is unaffected.
    assert guard.should_handle("agent1y", "a", now=0.3)


def test_reset_clears_burst_state():
    guard = EchoGuard(cooldown_seconds=0.0, max_burst=2, burst_window_seconds=10.0)
    guard.should_handle("agent1x", "a", now=0.0)
    guard.should_handle("agent1x", "b", now=0.1)
    assert not guard.should_handle("agent1x", "c", now=0.2)
    guard.reset()
    assert guard.should_handle("agent1x", "c", now=0.3)


def test_normalise_strips_punctuation_and_case():
    assert normalise("  Hello, World!  ") == "hello world"


# --- card selection parsing ---------------------------------------------------


def test_parse_json_selection():
    payload = json.dumps({"event_id": "cornucopia", "source": "events_tab"})
    parsed = parse_card_selection(payload, id_field="event_id")
    assert parsed == {"event_id": "cornucopia", "source": "events_tab"}


def test_parse_prose_selection():
    text = "The user picked event_id ph_farm_tour from events_tab."
    parsed = parse_card_selection(text, id_field="event_id")
    assert parsed is not None
    assert parsed["event_id"] == "ph_farm_tour"


def test_parse_back_action():
    parsed = parse_card_selection(
        json.dumps({"action": "back_to_events"}), id_field="event_id"
    )
    assert parsed == {"action": "back_to_events"}


def test_parse_back_action_from_prose():
    parsed = parse_card_selection("please go back_to_clubs now", id_field="club_id")
    assert parsed is not None
    assert parsed["action"] == "back_to_clubs"


def test_parse_ignores_ordinary_text():
    assert parse_card_selection("what's happening Wednesday", id_field="event_id") is None
    assert parse_card_selection("", id_field="event_id") is None


def test_parse_is_scoped_to_the_id_field():
    text = json.dumps({"club_id": "c_anime"})
    assert parse_card_selection(text, id_field="event_id") is None
    assert parse_card_selection(text, id_field="club_id") == {"club_id": "c_anime"}


# --- card payloads ------------------------------------------------------------


def test_list_payload_shape():
    items = [
        CardItem(record_id="a", heading="A", body="body a", badges=[("Confirmed", "success")]),
        CardItem(record_id="b", heading="B", body="body b"),
    ]
    payload = build_list_payload(
        items, title="Things", subtitle="Tap one", id_field="event_id", source="events_tab"
    )
    root = payload["root"]
    assert root["type"] == "section"
    assert root["title"] == "Things"
    assert root["subtitle"] == "Tap one"

    listing = root["children"][0]
    assert listing["type"] == "list"
    assert len(listing["items"]) == 2

    button = listing["items"][0]["children"][-1]
    assert button["type"] == "button"
    assert button["action"]["selection"] == {
        "event_id": "a",
        "source": "events_tab",
    }


def test_list_payload_omits_absent_subtitle():
    payload = build_list_payload(
        [], title="Empty", subtitle=None, id_field="event_id", source="events_tab"
    )
    assert "subtitle" not in payload["root"]


def test_detail_payload_includes_rows_and_back_button():
    payload = build_detail_payload(
        title="Cornucopia",
        heading="Cornucopia",
        body="A festival.",
        badges=[("Confirmed", "success")],
        rows=[DetailRow("Date", "Tuesday Sep 22")],
        footnote="Check the official page.",
        back_label="Back",
        back_action="back_to_events",
        source="events_tab",
    )
    root = payload["root"]
    column = root["children"][0]["children"]
    assert any(node.get("type") == "divider" for node in column)
    assert any("Date: Tuesday Sep 22" == node.get("value") for node in column)

    back = root["children"][1]["children"][0]
    assert back["action"]["selection"]["action"] == "back_to_events"


def test_card_metadata_is_json_encoded():
    metadata = card_metadata({"root": {"type": "section", "children": []}})
    assert isinstance(metadata, MetadataContent)
    assert metadata.metadata["card_protocol_version"] == "1"
    assert json.loads(metadata.metadata["card_payload"])["root"]["type"] == "section"


def test_card_message_carries_text_then_card_and_stays_open():
    message = card_message("here you go", {"root": {"type": "section", "children": []}})
    kinds = [type(item) for item in message.content]
    assert kinds[0] is TextContent
    assert MetadataContent in kinds
    # A card message must not end the session, or taps cannot be answered.
    assert not any(isinstance(item, EndSessionContent) for item in message.content)


# --- chat helpers and notices -------------------------------------------------


def test_create_text_chat_can_end_session():
    plain = create_text_chat("hello")
    assert not any(isinstance(item, EndSessionContent) for item in plain.content)

    closing = create_text_chat("bye", end_session=True)
    assert any(isinstance(item, EndSessionContent) for item in closing.content)


def test_notices_distinguish_verified_state():
    assert badge(True) == ("Confirmed", "success")
    assert badge(False) == ("Unofficial", "warning")
    assert marker(True) == ""
    assert "unofficial" in marker(False)


def test_event_time_never_invents_a_value():
    assert event_time(None) == "time not yet published"
    assert event_time("") == "time not yet published"
    assert event_time("7:00 PM") == "7:00 PM"


# --- conversation replay ------------------------------------------------------
# ASI:One re-sends the whole conversation on every turn: one tap arrives with
# the original question and every earlier tap behind it. Answering all of them
# costs several round trips per tap and delays the card actually asked for.


def test_replay_is_dropped_when_something_newer_follows():
    """The replayed prefix of a burst is dropped."""
    import asyncio

    from common.guard import EchoGuard, is_stale_replay

    guard = EchoGuard()
    sender = "agent1x"

    async def scenario():
        # Turn one: the student asks, and taps a button.
        first = guard.note_inbound(sender)
        assert not await is_stale_replay(guard, sender, "tell me about clubs", first, hold=0.05)
        guard.mark_answered(sender, "tell me about clubs")

        second = guard.note_inbound(sender)
        assert not await is_stale_replay(guard, sender, "categories", second, hold=0.05)
        guard.mark_answered(sender, "categories")

        # Turn two: the client replays both, then delivers the new tap. The
        # replayed pair is held; the newer arrival lands while they wait.
        replay_a = guard.note_inbound(sender)
        replay_b = guard.note_inbound(sender)
        newest = guard.note_inbound(sender)

        assert await is_stale_replay(guard, sender, "tell me about clubs", replay_a, hold=0.05)
        assert await is_stale_replay(guard, sender, "categories", replay_b, hold=0.05)
        # The message the student actually sent is new, so it never waits.
        assert not await is_stale_replay(guard, sender, "spiritual", newest, hold=0.05)

    asyncio.run(scenario())


def test_a_deliberate_repeat_is_still_answered():
    """The failure mode that matters: a student re-tapping the same button, or
    re-asking the same question, must not meet silence."""
    import asyncio

    from common.guard import EchoGuard, is_stale_replay

    guard = EchoGuard()
    sender = "agent1x"

    async def scenario():
        first = guard.note_inbound(sender)
        assert not await is_stale_replay(guard, sender, "spiritual", first, hold=0.05)
        guard.mark_answered(sender, "spiritual")

        # Same tap again, with nothing behind it. Held briefly, then answered.
        again = guard.note_inbound(sender)
        assert not await is_stale_replay(guard, sender, "spiritual", again, hold=0.05)

    asyncio.run(scenario())


def test_new_messages_are_never_delayed():
    """The common path must cost nothing: an unseen message returns without
    waiting at all."""
    import asyncio
    import time

    from common.guard import EchoGuard, is_stale_replay

    guard = EchoGuard()

    async def scenario():
        sequence = guard.note_inbound("agent1x")
        started = time.perf_counter()
        stale = await is_stale_replay(
            guard, "agent1x", "something new", sequence, hold=5.0
        )
        elapsed = time.perf_counter() - started
        assert not stale
        assert elapsed < 0.05, f"new message waited {elapsed:.2f}s"

    asyncio.run(scenario())


def test_agents_handle_messages_concurrently():
    """The replay defence depends on it.

    common/guard.is_stale_replay holds a message it has already answered to see
    whether a newer one arrives behind it. uagents processes messages one at a
    time by default, which would make the held message block the very arrival
    it is waiting for — it would wait out the hold, conclude it was newest, and
    answer anyway, with every other replayed message queued behind it doing the
    same. Turning this off would not fail loudly; it would just make every tap
    slow again.
    """
    from common.transport import agent_kwargs

    kwargs = agent_kwargs(name="t", seed="s", port=1)
    assert kwargs.get("handle_messages_concurrently") is True
