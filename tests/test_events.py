"""Event date resolution, filtering, and ranking."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from agents.events.recommend import (
    EventQuery,
    build_query,
    by_id,
    detect_college,
    detect_tags,
    resolve_dates,
    select,
    weekday_name,
    window_dates,
)
from agents.events.service import respond_to_query, respond_to_selection
from uagents_core.contrib.protocols.chat import MetadataContent, TextContent

DURING = date(2026, 9, 22)  # Tuesday of Welcome Week
BEFORE = date(2026, 8, 9)
AFTER = date(2026, 10, 5)


def _text(message) -> str:
    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def _card_text(message) -> str:
    """Everything rendered on the card, footnote included."""
    for item in message.content:
        if isinstance(item, MetadataContent):
            return item.metadata["card_payload"]
    return ""


def _has_card(message) -> bool:
    return any(isinstance(item, MetadataContent) for item in message.content)


# --- date resolution ----------------------------------------------------------


def test_window_is_six_days_monday_to_saturday():
    dates = window_dates()
    assert dates == [
        "2026-09-21",
        "2026-09-22",
        "2026-09-23",
        "2026-09-24",
        "2026-09-25",
        "2026-09-26",
    ]
    assert weekday_name("2026-09-21") == "Monday"
    assert weekday_name("2026-09-26") == "Saturday"


def test_today_inside_window():
    resolution = resolve_dates("what's happening today", DURING)
    assert resolution.dates == ["2026-09-22"]
    assert resolution.note is None


def test_today_before_window_explains_and_falls_back():
    resolution = resolve_dates("what's on today", BEFORE)
    assert resolution.dates == ["2026-09-21"]
    assert resolution.note is not None
    assert "hasn't started" in resolution.note


def test_today_after_window_returns_no_dates():
    resolution = resolve_dates("what's on tonight", AFTER)
    assert resolution.dates == []
    assert resolution.note is not None
    assert "finished" in resolution.note


def test_tomorrow_inside_window():
    resolution = resolve_dates("anything tomorrow", DURING)
    assert resolution.dates == ["2026-09-23"]


def test_tomorrow_outside_window_is_explained():
    resolution = resolve_dates("anything tomorrow", date(2026, 9, 26))
    assert resolution.note is not None


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("monday", "2026-09-21"),
        ("Tuesday", "2026-09-22"),
        ("wed", "2026-09-23"),
        ("thursday", "2026-09-24"),
        ("Friday", "2026-09-25"),
        ("sat", "2026-09-26"),
    ],
)
def test_weekday_names_resolve(phrase, expected):
    assert resolve_dates(f"events on {phrase}", DURING).dates == [expected]


def test_sunday_is_rejected_with_explanation():
    resolution = resolve_dates("events on sunday", DURING)
    assert resolution.dates == []
    assert resolution.note is not None
    assert "no Sunday" in resolution.note


def test_explicit_day_of_month():
    assert resolve_dates("what's on sept 23", DURING).dates == ["2026-09-23"]
    assert resolve_dates("the 25th", DURING).dates == ["2026-09-25"]


def test_day_outside_window_is_explained():
    resolution = resolve_dates("events on september 30", DURING)
    assert resolution.dates == []
    assert "outside Welcome Week" in (resolution.note or "")


def test_whole_week_returns_all_days():
    assert resolve_dates("show me the whole week", DURING).dates == window_dates()


# --- filters ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("events for Crown students", "Crown"),
        ("anything at college nine", "College Nine"),
        ("c10 events", "John R. Lewis"),
        ("college ten", "John R. Lewis"),
        ("rachel carson stuff", "Rachel Carson"),
        ("porter college", "Porter"),
    ],
)
def test_detect_college(text, expected):
    assert detect_college(text) == expected


def test_detect_college_none_when_absent():
    assert detect_college("what's on Wednesday") is None


def test_detect_tags_from_interests():
    assert "food" in detect_tags("free food")
    assert "sports" in detect_tags("any sports")
    assert "outdoors" in detect_tags("outdoor stuff")
    assert "career" in detect_tags("looking for a job")


# --- selection and ranking ----------------------------------------------------


def test_confirmed_events_always_rank_above_placeholders():
    query = build_query("events for Crown students", DURING)
    scored, _ = select(query, limit=20)
    verified = [item.event["verified"] for item in scored]
    # Once we see a placeholder, no confirmed event may follow.
    assert verified == sorted(verified, reverse=True), verified


def test_select_returns_total_for_truncation():
    query = build_query("show me the whole week", DURING)
    scored, total = select(query, limit=3)
    assert len(scored) == 3
    assert total > 3


def test_day_filter_only_returns_that_day():
    query = build_query("what's happening Wednesday", DURING)
    scored, _ = select(query, limit=20)
    assert scored
    assert {item.event["date"] for item in scored} == {"2026-09-23"}


def test_college_filter_excludes_other_colleges():
    query = build_query("events for Porter students", DURING)
    scored, _ = select(query, limit=20)
    assert scored
    for item in scored:
        scope = item.event["college_scope"]
        assert scope == "all" or "Porter" in scope


def test_college_specific_event_is_excluded_for_other_colleges():
    """Porter Arts Night is scoped to Porter and Kresge only."""
    query = EventQuery(college="Cowell")
    scored, _ = select(query, limit=50)
    ids = {item.event["id"] for item in scored}
    assert "ph_porter_arts_night" not in ids


def test_interest_filter_requires_a_tag_match():
    query = build_query("music events", DURING)
    scored, _ = select(query, limit=20)
    assert scored
    for item in scored:
        assert {"music", "arts"} & set(item.event["tags"])


def test_no_matches_returns_empty():
    query = EventQuery(dates=["2026-09-21"], tags={"nonexistent-tag-xyz"})
    scored, total = select(query)
    assert scored == []
    assert total == 0


# --- verified data contract ---------------------------------------------------


def test_confirmed_events_never_have_an_invented_time():
    """The official page publishes no times, so confirmed times must be null."""
    from common.loader import events

    for event in events():
        if event["verified"]:
            assert event["time"] is None, (
                f"{event['id']} is marked verified but carries a time — the official "
                "source does not publish times, so this would be fabricated"
            )


def test_the_five_confirmed_events_are_present():
    expected = {
        "new_admit_class_photo",
        "late_night_athletics_rec",
        "cornucopia",
        "student_employment_fair",
        "boardwalk_frolic",
        "choose_your_own_slugventure",
    }
    for event_id in expected:
        event = by_id(event_id)
        assert event is not None, event_id
        assert event["verified"] is True, event_id
        assert event["source"], event_id


# --- responses ----------------------------------------------------------------


def test_response_includes_card_and_standalone_text():
    message, ids = asyncio.run(
        respond_to_query("what's happening Wednesday", today=DURING)
    )
    assert ids
    assert _has_card(message)
    # The day and the events are on the card; the bubble is the source link.
    assert "Wednesday" in _card_text(message)
    assert "welcome.ucsc.edu" in _text(message)


def test_response_labels_placeholders():
    """Placeholder entries carry an Unofficial badge on their card item."""
    message, _ = asyncio.run(respond_to_query("show me the whole week", today=DURING))
    assert "Unofficial" in _card_text(message)


def test_response_states_time_not_published():
    """Events render on the card, so the refusal to invent a time lives in the
    card item body rather than the text bubble."""
    message, shown_ids = asyncio.run(
        respond_to_query("what's on Monday", today=DURING)
    )
    assert shown_ids

    payload = json.loads(
        next(
            item for item in message.content if isinstance(item, MetadataContent)
        ).metadata["card_payload"]
    )
    assert "time not yet published" in json.dumps(payload)


def test_out_of_window_query_is_explained():
    message, _ = asyncio.run(respond_to_query("what's on tonight", today=BEFORE))
    assert "hasn't started" in _text(message)


def test_selection_detail_for_confirmed_event():
    message = respond_to_selection("cornucopia")
    rendered = _text(message) + _card_text(message)
    assert "Cornucopia" in rendered
    assert "East Upper Field" in rendered
    # The confirmed event itself must carry no placeholder warning. Other events
    # listed under "Also on <day>" are legitimately labelled unofficial, so
    # the check is scoped to this event's own copy.
    own_copy = rendered.split("Also on")[0]
    assert "Placeholder example" not in own_copy
    assert "unofficial" not in own_copy.lower()


def test_selection_detail_warns_on_placeholder():
    message = respond_to_selection("ph_porter_arts_night")
    assert "Placeholder example" in _text(message) + _card_text(message)


def test_unknown_selection_is_handled():
    body = _text(respond_to_selection("nope_not_real"))
    assert "lost track" in body


# --- approximate-match labelling ------------------------------------------

from agents.events.service import _heading as events_heading
from agents.events.recommend import EventQuery, ScoredEvent


def _scored_events(n):
    return [ScoredEvent(event={"id": f"e{i}"}, score=1.0) for i in range(n)]


def test_events_approximate_query_is_labelled():
    query = EventQuery(tags={"social"}, approximate=True)
    heading = events_heading(query, _scored_events(4), 4, "vibes and good energy")
    assert "Closest matches" in heading


def test_events_day_filter_stays_authoritative_even_when_approximate():
    """A specific date is a real filter regardless of how the tags were derived."""
    query = EventQuery(dates=["2026-09-23"], tags={"food"}, approximate=True)
    heading = events_heading(query, _scored_events(4), 4, "snacks on wednesday")
    assert "Wednesday" in heading
    assert "Closest matches" not in heading
