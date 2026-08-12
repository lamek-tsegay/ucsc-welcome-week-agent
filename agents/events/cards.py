"""Card and text rendering for the events agent."""

from __future__ import annotations

from datetime import date

from agents.events.recommend import ScoredEvent, weekday_name, window_dates
from common.cards import (
    CardItem,
    DetailBlock,
    DetailRow,
    MenuButton,
    build_chip_payload,
    build_detail_payload,
    build_list_payload,
    card_message,
    menu_message,
)
from common.chat import create_text_chat
from common.colleges import COLLEGES
from common.links import essentials_text, link_row
from common.loader import events_window, landmark_name
from common.notices import (
    OFFICIAL_EVENTS_URL,
    badge,
    event_time,
    events_disclaimer,
    events_footnote,
    marker,
)
from uagents_core.contrib.protocols.chat import ChatMessage

# First matching tag wins; order goes from specific to generic. Purely visual
# — an unknown tag simply gets no emoji, never a wrong one.
_TAG_EMOJI = [
    ("festival", "🎪"), ("food", "🍕"), ("music", "🎶"), ("photo", "📸"),
    ("sports", "🏅"), ("outdoors", "🌲"), ("jobs", "💼"), ("career", "💼"),
    ("tech", "💻"), ("cultural", "🌍"), ("wellness", "🧘"), ("arts", "🎨"),
    ("tour", "🚶"), ("orgs", "🤝"), ("tradition", "🐌"), ("transfer", "🔄"),
    ("orientation", "🧭"), ("academic", "📚"), ("recreation", "🏓"),
    ("offcampus", "🚌"), ("social", "🎉"), ("evening", "🌙"),
]


def tag_emoji(tags: list[str] | set[str]) -> str:
    tag_set = set(tags or [])
    for tag, emoji in _TAG_EMOJI:
        if tag in tag_set:
            return emoji
    return ""


def _title_with_emoji(event: dict) -> str:
    emoji = tag_emoji(event.get("tags", []))
    return f"{emoji} {event['title']}".strip()


EVENT_ID_FIELD = "event_id"
SOURCE = "events_tab"
BACK_ACTION = "back_to_events"

# Selection keys this agent's buttons carry beyond the event id.
EXTRA_FIELDS = ("college", "date", "q", "vibe")

# Six ways into the week, for a student who doesn't know what's on. Mirrors the
# clubs agent's vibe matcher: nobody can pick from a schedule they've never
# seen, but everyone can say what they're in the mood for. Every tag here
# exists in data/events.json — a test enforces that each interest matches at
# least one event, so no option can dead-end.
VIBES: list[tuple[str, str, str, set[str]]] = [
    ("food", "🍕 Free food", "meals and snacks", {"food"}),
    ("social", "🎉 Meet people", "socials and traditions",
     {"social", "orgs", "tradition", "festival"}),
    ("active", "🌲 Outdoors & active", "moving around campus",
     {"outdoors", "sports", "recreation"}),
    ("arts", "🎨 Arts & music", "performances and making things",
     {"arts", "music", "photo"}),
    ("career", "💼 Career & academic", "jobs and getting set up",
     {"academic", "career", "jobs", "tech"}),
    ("explore", "🚌 Off campus", "the town and the coast",
     {"offcampus", "tour", "exploration"}),
]

VIBE_TAGS = {key: tags for key, _, _, tags in VIBES}
VIBE_LABELS = {key: label for key, label, _, _ in VIBES}


def _interest_buttons() -> list[MenuButton]:
    return [
        MenuButton(label, {"action": "vibe_pick", "vibe": key})
        for key, label, _, _ in VIBES
    ]


def interests_message() -> ChatMessage:
    """The first reply to a general ask about Welcome Week.

    Twenty-two events across six days is not something a new student can pick
    from cold, but anyone can say what they're in the mood for. So the opening
    move is the question; the whole week stays one tap away.
    """
    preamble = (
        "Welcome to Slug Start! 🎪 Six days, Sept 21–26.\n\n"
        "**What are you in the mood for?** Tap one below, or just ask me — "
        "*what's on Wednesday*, *free food Friday*, *plan my Tuesday* all work."
    )
    footer = [MenuButton("📅 Browse by day", {"action": "plan_day"})]
    payload = build_chip_payload(
        title="What are you into? 🎪",
        subtitle="Tap one — I'll show you what fits",
        body_lines=None,
        chips=_interest_buttons(),
        source=SOURCE,
        footer_buttons=footer,
        per_row=1,
    )
    return card_message(preamble, payload)


def vibe_picker_message() -> ChatMessage:
    """The same question, reached deliberately from a button."""
    preamble = (
        "**What are you in the mood for?** Tap whichever fits — or just "
        "describe it in your own words."
    )
    footer = [MenuButton("📅 Browse by day", {"action": "plan_day"})]
    payload = build_chip_payload(
        title="What are you into? 🎪",
        subtitle="Tap one — I'll show you what fits",
        body_lines=None,
        chips=_interest_buttons(),
        source=SOURCE,
        footer_buttons=footer,
        per_row=1,
    )
    return card_message(preamble, payload)


def welcome() -> str:
    window = events_window()
    return (
        f"Hi — I'm the **UCSC Welcome Week Events** agent for "
        f"**{window['label']}**.\n\n"
        "Ask me things like:\n"
        "• *what's happening Wednesday*\n"
        "• *any events for Crown students*\n"
        "• *free food this week*\n"
        "• *plan my Tuesday*\n"
        "• *show me the whole week*\n\n"
        "Tap an event for its date, venue, and who it's for.\n\n"
        "Two things to know up front: the official page publishes **dates but not "
        "times**, so I'll say when a time isn't published rather than guess. And "
        "some entries in my data are **placeholder examples** — I label those "
        "clearly.\n\n"
        "For walking directions to any venue, ask the **UCSC Campus "
        "Navigation** agent. For organizations to join, ask **UCSC Clubs & "
        "Societies**."
    )


def short_welcome(college_name: str | None) -> str:
    """Two sentences, not a wall of text. The long version lives behind ℹ️."""
    hello = (
        f"Hey! 👋 I'm your **Welcome Week events** guide — Sept 21–26, "
        "all six days."
    )
    if college_name:
        hello += f" You're at **{college_name}**, so I'll keep that in mind."
    return (
        hello
        + "\n\nTap a button, or just talk to me: *free food Friday*, "
        "*plan my Tuesday*, *what's on tonight*.\n\n"
        "_Confirmed events always come first — anything unofficial is labelled._"
    )


def welcome_message(college_name: str | None) -> ChatMessage:
    """Welcome menu: the four things every new student actually asks."""
    body = (
        [f"🎓 Your saved college: {college_name}"]
        if college_name
        else ["Tap 🎓 to save your college — UCSC's first-day programming depends on it."]
    )
    # Two ways in — by interest or by day — and nothing else competing with
    # them. Whole week, Plan my day, and Free food were three more doors into
    # the same 22 events.
    buttons = [
        MenuButton("🎯 What are you into", {"action": "quiz"}, primary=True),
        MenuButton("📅 Browse by day", {"action": "plan_day"}),
        MenuButton(
            "🎓 My college" if college_name else "🎓 Set my college",
            {"action": "my_college"},
        ),
        MenuButton("🔗 Campus links", {"action": "links"}),
        MenuButton("ℹ️ About my data", {"action": "about"}),
    ]
    return menu_message(
        short_welcome(college_name),
        title="UCSC Welcome Week Events 🎪",
        subtitle="Sept 21–26 · confirmed events always listed first",
        body_lines=body,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def about_message() -> ChatMessage:
    """The full story: capabilities, examples, and the data-honesty rules."""
    return create_text_chat(welcome())


def links_message() -> ChatMessage:
    return create_text_chat(essentials_text())


def college_picker_message(*, note: str | None = None) -> ChatMessage:
    """College buttons. UCSC's first-day programming is college-specific, so
    this genuinely changes which events are relevant."""
    preamble = (note + "\n\n" if note else "") + (
        "Which residential college are you in? I'll use it to filter events — "
        "UCSC's first-day programming depends on it."
    )
    buttons = [
        MenuButton(
            f"{college.emoji} {college.name}",
            {"action": "set_college", "college": college.key},
        )
        for college in COLLEGES
    ]
    return menu_message(
        preamble,
        title="Set your college 🎓",
        subtitle="UCSC's first-day programming depends on it",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def day_picker_message() -> ChatMessage:
    """One button per Welcome Week day — the twin of the clubs category picker."""
    buttons = [
        MenuButton(
            f"{weekday_name(iso)[:3]} {date.fromisoformat(iso).strftime('%b %-d')}",
            {"action": "plan_day", "date": iso},
        )
        for iso in window_dates()
    ]
    buttons.append(MenuButton("🎯 What are you into", {"action": "quiz"}))
    return menu_message(
        "Which day?",
        title="Browse by day 📅",
        subtitle="Tap a day to see what's on",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=3,
    )


def _day_label(iso: str) -> str:
    parsed = date.fromisoformat(iso)
    return f"{weekday_name(iso)} {parsed.strftime('%b %-d')}"


def _location_text(event: dict) -> str:
    note = event.get("location_note")
    if note:
        return note
    return landmark_name(event.get("location_id"), "location TBC")


def _summary_line(event: dict) -> str:
    return (
        f"• {marker(event['verified'])}**{_title_with_emoji(event)}** — "
        f"{_day_label(event['date'])}, {event_time(event.get('time'))}"
    )


def _scope_text(event: dict) -> str:
    scope = event.get("college_scope", "all")
    if scope == "all":
        return "All new students"
    if isinstance(scope, list):
        return ", ".join(scope) + " colleges"
    return str(scope)


def list_message(
    scored: list[ScoredEvent],
    *,
    heading: str,
    date_note: str | None,
    footer_buttons: list[MenuButton] | None = None,
) -> ChatMessage:
    """The list card, plus a text bubble carrying the heading and caveats.

    The events themselves live only on the card, which shows each one's title,
    day, time, venue, and Confirmed/Unofficial badge. Repeating them as text
    printed the whole schedule twice. Time and verification labelling move to
    the card items, where the honesty gate checks them.
    """
    any_unverified = any(not item.event["verified"] for item in scored)

    lines: list[str] = []
    if date_note:
        lines.append(f"ℹ️ {date_note}\n")
    # No URL in the bubble: the client unfurls any link into a preview box,
    # which on a listing is noise. The schedule link stays on the card footnote.
    lines.append(heading)
    preamble = "\n".join(lines)

    items = [
        CardItem(
            record_id=item.event["id"],
            heading=_title_with_emoji(item.event),
            body=(
                f"{_day_label(item.event['date'])} · {event_time(item.event.get('time'))}"
                f" · {_location_text(item.event)}"
            ),
            badges=[badge(item.event["verified"])],
            button_label="Details",
        )
        for item in scored
    ]

    payload = build_list_payload(
        items,
        title=heading.replace("**", ""),
        subtitle="Tap an event for details",
        id_field=EVENT_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer_buttons,
        footnote=events_footnote(any_unverified=any_unverified),
    )
    return card_message(preamble, payload)


def detail_message(event: dict, others: list[dict]) -> ChatMessage:
    """Detail card for one event."""
    verified = event["verified"]

    rows = [
        DetailRow("Date", _day_label(event["date"])),
        DetailRow("Time", event_time(event.get("time"))),
        DetailRow("Where", _location_text(event)),
        DetailRow("Who", _scope_text(event)),
    ]

    blocks = []
    if others:
        blocks.append(
            DetailBlock(
                f"Also on {_day_label(event['date'])}",
                [
                    " · ".join(
                        f"{marker(other['verified'])}{other['title']}"
                        for other in others
                    )
                ],
            )
        )

    if verified:
        footnote = f"Date confirmed: {OFFICIAL_EVENTS_URL}"
        if not event.get("time"):
            footnote = (
                "Date confirmed on the official page, which has not published a "
                f"time yet. Check {OFFICIAL_EVENTS_URL} closer to the day."
            )
    else:
        footnote = (
            "⚠️ Placeholder example from this agent's seed data, not an "
            f"announced event. Confirm at {OFFICIAL_EVENTS_URL}."
        )

    # A link button rather than a URL in the bubble, which the client would
    # unfurl into a preview box. The selection travels too, so a client that
    # ignores the url still sends the tap and gets the address back as text.
    extra_buttons: list[MenuButton] = [
        MenuButton(
            "📅 Official schedule",
            {"action": "open_schedule"},
            url=OFFICIAL_EVENTS_URL,
        )
    ]

    payload = build_detail_payload(
        title=event["title"],
        heading=event["title"],
        body=event["description"],
        badges=[badge(verified)],
        rows=rows,
        blocks=blocks,
        footnote=footnote,
        back_label="Back",
        back_action=BACK_ACTION,
        source=SOURCE,
        extra_buttons=extra_buttons,
    )

    # No URL in the bubble: the schedule link is a button on the card, so
    # there is nothing here for the client to unfurl into a preview.
    return card_message(f"**{event['title']}**", payload)


def planner_message(
    iso_date: str,
    scored: list[ScoredEvent],
) -> ChatMessage:
    """A one-day menu of what's on, confirmed events first.

    The framing matters: the university has published dates but no times, so
    this is deliberately a *menu for the day*, never a schedule. Ordering
    implies nothing about when things happen — confirmed events simply sort
    first, same as everywhere else.
    """
    day = _day_label(iso_date)

    items = [
        CardItem(
            record_id=item.event["id"],
            heading=item.event["title"],
            body=(
                f"{_location_text(item.event)} · "
                f"{event_time(item.event.get('time'))}"
            ),
            badges=[badge(item.event["verified"])],
            button_label="Details",
        )
        for item in scored
    ]
    footer = [
        MenuButton("📅 Other days", {"action": "plan_day"}),
        MenuButton("🎯 What are you into", {"action": "quiz"}),
    ]
    payload = build_list_payload(
        items,
        title=f"{day} — your menu 🧭",
        subtitle="Confirmed first · times not yet published",
        id_field=EVENT_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer,
        footnote=events_footnote(
            any_unverified=any(not item.event["verified"] for item in scored)
        ),
    )
    return card_message(f"**{day} — your menu** 🧭", payload)


def no_matches_message(
    *, date_note: str | None, had_filters: bool
) -> ChatMessage:
    lines = []
    if date_note:
        lines.append(f"ℹ️ {date_note}")
        lines.append("")

    if had_filters:
        lines.append(
            "I don't have anything matching that. Try loosening it — a different day, "
            "or a broader interest like *food*, *music*, *sports*, or *outdoors*."
        )
    else:
        lines.append(
            "I don't have any events for that. Welcome Week runs "
            "**Monday Sept 21 – Saturday Sept 26**; try *what's happening Tuesday* "
            "or *show me the whole week*."
        )

    lines.append("")
    lines.append(f"The official schedule lives at {OFFICIAL_EVENTS_URL}.")

    buttons = [
        MenuButton(
            "🗓️ Whole week",
            {"action": "quick", "q": "show me the whole week"},
            primary=True,
        ),
        MenuButton("🧭 Plan a day", {"action": "plan_day"}),
        MenuButton("🍕 Free food", {"action": "quick", "q": "free food this week"}),
    ]
    return menu_message(
        "\n".join(lines),
        title="Nothing matched — try these 🎪",
        subtitle=None,
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def stale_selection_message() -> ChatMessage:
    return create_text_chat(
        "I've lost track of that event — ask me for the schedule again and tap "
        "from the fresh list."
    )
