"""Card and text rendering for the events agent."""

from __future__ import annotations

from datetime import date

from agents.events.recommend import ScoredEvent, weekday_name, window_dates
from common.cards import (
    CardItem,
    DetailBlock,
    DetailRow,
    MenuButton,
    build_detail_payload,
    build_list_payload,
    card_message,
    menu_message,
)
from common.chat import create_text_chat
from common.colleges import COLLEGES
from common.links import essentials_text, link_row
from common.loader import events_window, landmark_name
from common.maps import PIN_CAVEAT, pin_line, pin_url
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
EXTRA_FIELDS = ("college", "date", "q")


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
        "Tap an event for details — including **walking directions from your "
        "college**, once you've told me which one you're in.\n\n"
        "Two things to know up front: the official page publishes **dates but not "
        "times**, so I'll say when a time isn't published rather than guess. And "
        "some entries in my data are **placeholder examples** — I label those "
        "clearly.\n\n"
        "For directions to a venue, ask the **UCSC Campus Navigation** agent. "
        "For organizations to join, ask **UCSC Clubs & Societies**."
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
        else ["Tap 🎓 to save your college — it unlocks event directions."]
    )
    buttons = [
        MenuButton(
            "🗓️ Whole week", {"action": "quick", "q": "show me the whole week"},
            primary=True,
        ),
        MenuButton("🍕 Free food", {"action": "quick", "q": "free food this week"}),
        MenuButton("🧭 Plan my day", {"action": "plan_day"}),
        MenuButton("⭐ My plan", {"action": "my_plan"}),
        MenuButton(
            "🎓 My college" if college_name else "🎓 Set my college",
            {"action": "my_college"},
        ),
    ]
    buttons.append(MenuButton("🔗 Campus links", {"action": "links"}))
    buttons.append(MenuButton("ℹ️ About my data", {"action": "about"}))
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


def college_picker_message(
    *, note: str | None = None, event_id: str | None = None
) -> ChatMessage:
    """College buttons; optionally carries the event the student was routing to.

    When `event_id` is set, choosing a college continues straight into
    directions for that event instead of making the student tap again.
    """
    preamble = (note + "\n\n" if note else "") + (
        "Which residential college are you in? I'll remember it for event "
        "recommendations and walking directions."
    )
    buttons = []
    for college in COLLEGES:
        selection = {"action": "set_college", "college": college.key}
        if event_id:
            selection[EVENT_ID_FIELD] = event_id
        buttons.append(MenuButton(f"{college.emoji} {college.name}", selection))
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
    """One button per Welcome Week day, for the planner."""
    buttons = [
        MenuButton(
            f"{weekday_name(iso)[:3]} {date.fromisoformat(iso).strftime('%b %-d')}",
            {"action": "plan_day", "date": iso},
        )
        for iso in window_dates()
    ]
    return menu_message(
        "Which day should I lay out for you?",
        title="Plan your day 🧭",
        subtitle="Confirmed events first, walking times included",
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
    lines.append(heading)
    lines.append("")
    lines.append(link_row(("Official schedule", OFFICIAL_EVENTS_URL)))
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
        footnote=events_footnote(any_unverified=any_unverified),
    )
    return card_message(preamble, payload)


def detail_message(
    event: dict, others: list[dict], *, saved: bool = False
) -> ChatMessage:
    """Detail card for one event. `saved` reflects the student's ⭐ state."""
    verified = event["verified"]

    rows = [
        DetailRow("Date", _day_label(event["date"])),
        DetailRow("Time", event_time(event.get("time"))),
        DetailRow("Where", _location_text(event)),
        DetailRow("Who", _scope_text(event)),
    ]

    blocks = []
    pin = pin_line(event["location_id"]) if event.get("location_id") else None
    if pin:
        blocks.append(DetailBlock("Getting there", [pin, PIN_CAVEAT.strip("_")]))
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

    # Directions only when the venue is actually known — an event whose location
    # is "not yet published" must not grow a button that pretends otherwise.
    extra_buttons = []
    if event.get("location_id"):
        extra_buttons.append(
            MenuButton(
                "🗺️ Directions",
                {EVENT_ID_FIELD: event["id"], "action": "directions"},
                primary=True,
            )
        )
    extra_buttons.append(
        MenuButton(
            "✅ In your plan" if saved else "⭐ Add to my plan",
            {EVENT_ID_FIELD: event["id"], "action": "save_event"},
        )
    )

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

    # The card carries the detail; the bubble carries the tappable links,
    # since card text is not clickable.
    pairs = []
    maps_url = pin_url(event["location_id"]) if event.get("location_id") else None
    if maps_url:
        pairs.append(("📍 Open in Maps", maps_url))
    pairs.append(("Official schedule", OFFICIAL_EVENTS_URL))

    preamble = (
        f"**{event['title']}** — {_day_label(event['date'])}\n\n"
        + link_row(*pairs)
    )
    return card_message(preamble, payload)


def planner_message(
    iso_date: str,
    scored: list[ScoredEvent],
    legs: list[tuple[str, str, int]],
) -> ChatMessage:
    """A one-day menu with walking times chained between venues.

    `legs` is (from_venue_name, to_venue_name, walk_minutes) for consecutive
    events whose venues are both known.

    The framing matters: the university has published dates but no times, so
    this is deliberately a *menu for the day*, never a schedule. Ordering
    implies nothing about when things happen — confirmed events simply sort
    first, same as everywhere else.
    """
    day = _day_label(iso_date)
    any_unverified = any(not item.event["verified"] for item in scored)

    lines = [f"**Your {day} menu** 🧭", ""]
    lines.append(
        "_Times aren't published yet, so this is a menu, not a schedule — "
        "confirmed events first, walking times to help you chain them._"
    )
    lines.append("")
    for item in scored:
        event = item.event
        lines.append(
            f"• {marker(event['verified'])}**{event['title']}** — "
            f"{_location_text(event)}, {event_time(event.get('time'))}"
        )
    if legs:
        lines.append("")
        lines.append("**Getting between venues** (walking estimates):")
        lines.extend(
            f"• {origin} → {dest}: about {minutes} min"
            for origin, dest, minutes in legs
        )
    lines.append("")
    lines.append(events_disclaimer(any_unverified=any_unverified))

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
        MenuButton("🗓️ Another day", {"action": "plan_day"}),
        MenuButton("📋 Whole week", {"action": "quick", "q": "show me the whole week"}),
    ]
    payload = build_list_payload(
        items,
        title=f"{day} — your menu 🧭",
        subtitle="Confirmed first · times not yet published",
        id_field=EVENT_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer,
    )
    return card_message("\n".join(lines), payload)


def empty_plan_message() -> ChatMessage:
    """Shown when ⭐ My plan has nothing in it yet."""
    preamble = (
        "**Your plan is empty so far.** ⭐\n\n"
        "Tap any event for details, then **⭐ Add to my plan** — I'll build "
        "you a personal Welcome Week itinerary with walking times between "
        "your picks."
    )
    buttons = [
        MenuButton(
            "🗓️ Browse the week",
            {"action": "quick", "q": "show me the whole week"},
            primary=True,
        ),
        MenuButton("🧭 Plan a day", {"action": "plan_day"}),
    ]
    return menu_message(
        preamble,
        title="My plan ⭐",
        subtitle="Star events to build your own itinerary",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def my_plan_message(
    chosen: list[dict],
    legs_by_date: dict[str, list[tuple[str, str, int]]],
) -> ChatMessage:
    """The student's starred events as a personal itinerary.

    Same honesty framing as the day planner: dates are real, times are not
    published, so within a day this is a set of picks, not a sequence.
    """
    any_unverified = any(not event["verified"] for event in chosen)

    lines = ["**Your Welcome Week plan** ⭐", ""]
    lines.append(
        "_Times aren't published yet — within each day these are your picks, "
        "not an order of events._"
    )
    for iso in sorted({event["date"] for event in chosen}):
        lines.append("")
        lines.append(f"**{_day_label(iso)}**")
        for event in (e for e in chosen if e["date"] == iso):
            lines.append(
                f"• {marker(event['verified'])}**{event['title']}** — "
                f"{_location_text(event)}, {event_time(event.get('time'))}"
            )
        for origin, dest, minutes in legs_by_date.get(iso, []):
            lines.append(f"   🚶 {origin} → {dest}: about {minutes} min")
    lines.append("")
    lines.append(events_disclaimer(any_unverified=any_unverified))

    items = [
        CardItem(
            record_id=event["id"],
            heading=event["title"],
            body=f"{_day_label(event['date'])} · {_location_text(event)}",
            badges=[badge(event["verified"])],
            button_label="Details",
        )
        for event in chosen
    ]
    footer = [
        MenuButton("🗓️ Add more", {"action": "quick", "q": "show me the whole week"}),
        MenuButton("🗑️ Clear my plan", {"action": "clear_plan"}),
    ]
    payload = build_list_payload(
        items,
        title="Your Welcome Week plan ⭐",
        subtitle=f"{len(chosen)} starred · tap for details",
        id_field=EVENT_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer,
    )
    return card_message("\n".join(lines), payload)


def directions_message(event: dict, origin_name: str, route_text: str) -> ChatMessage:
    """Walking directions to an event's venue, from the student's college."""
    lines = [
        f"**Getting to {event['title']}** — {_location_text(event)}",
        f"_Starting from {origin_name}, your saved college._",
        "",
        route_text,
    ]
    if not event["verified"]:
        lines.append("")
        lines.append(
            "⚠️ *Reminder: this event is a placeholder example, not an announced "
            f"event. Confirm at {OFFICIAL_EVENTS_URL} before walking anywhere.*"
        )
    return create_text_chat("\n".join(lines))


def plan_toggled_message(event: dict, *, saved: bool, total: int) -> ChatMessage:
    """Confirmation after ⭐, with no card — same reasoning as the clubs one."""
    if saved:
        count = (
            "that's your first one" if total == 1 else f"that's {total} saved"
        )
        text = (
            f"⭐ Added **{event['title']}** to your plan — {count}.\n\n"
            "Want to add more? Say *plan my Tuesday* or *show me the whole "
            "week*, or *my plan* to see your picks with walking times."
        )
    else:
        remaining = (
            "your plan is empty now" if total == 0 else f"{total} still saved"
        )
        text = (
            f"Removed **{event['title']}** from your plan — {remaining}.\n\n"
            "Want to look at more events?"
        )
    return create_text_chat(text)


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
