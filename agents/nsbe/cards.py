"""Card rendering for the NSBE chapter agent.

Same shape as the other three: the card carries the content, the bubble carries
only what a card cannot — tappable links, which are plain text inside a card.

The honesty rule differs from the clubs agent in one specific way. That agent
stores no contact or meeting details at all, because for most organizations
they would be guesses. This chapter publishes both on its own official page, so
they are stated here — with where they came from, when the page was read, and a
pointer to Instagram, which is where a change would actually be announced. A
meeting time is the one fact most likely to go stale without the page changing,
so it never appears without that caveat.
"""

from __future__ import annotations

from common.cards import MenuButton, build_chip_payload, card_message, menu_message
from common.chat import create_text_chat
from common.links import link_row
from common.loader import nsbe
from uagents_core.contrib.protocols.chat import ChatMessage

SOURCE = "nsbe_tab"
EXTRA_FIELDS = ("topic", "link")


def _sources() -> dict:
    return nsbe()["_meta"]["sources"]


def _checked(source_id: str) -> str:
    return _sources()[source_id]["checked"]


def _link(link_id: str) -> dict:
    return next(item for item in nsbe()["links"] if item["id"] == link_id)


def _instagram_note() -> str:
    """The line that keeps a published fact from being read as a promise."""
    return (
        f"_From their site, read {_checked('chapter_site')}. Meeting details can "
        f"change between terms without the page changing — "
        f"[Instagram]({_link('instagram')['url']}) is where they announce it._"
    )


def welcome_message() -> ChatMessage:
    chapter = nsbe()["chapter"]
    preamble = (
        f"Hey! 👋 I'm the **{chapter['short_name']}** agent — the UC Santa Cruz "
        "chapter of the National Society of Black Engineers.\n\n"
        f"{chapter['about']}\n\n"
        "What would you like to know?"
    )
    buttons = [
        MenuButton("📅 When they meet", {"action": "topic", "topic": "meetings"}, primary=True),
        MenuButton("🤝 How to join", {"action": "topic", "topic": "join"}),
        MenuButton("🎯 What NSBE is", {"action": "topic", "topic": "about"}),
        MenuButton("🔗 Their links", {"action": "topic", "topic": "links"}),
    ]
    return menu_message(
        preamble,
        title="UCSC NSBE 🛠️",
        subtitle="National Society of Black Engineers · UC Santa Cruz",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def meetings_message() -> ChatMessage:
    meetings = nsbe()["meetings"]
    preamble = (
        f"**{meetings['day']} at {meetings['time']}**\n"
        f"{meetings['location']}\n\n"
        "Anyone can turn up — you don't need to be a member, and the chapter "
        "welcomes all majors and ethnicities.\n\n" + _instagram_note()
    )
    buttons = [
        MenuButton("🤝 How to join", {"action": "topic", "topic": "join"}, primary=True),
        MenuButton("🔗 Their links", {"action": "topic", "topic": "links"}),
        MenuButton("↩️ Back", {"action": "topic", "topic": "home"}),
    ]
    return menu_message(
        preamble,
        title="Meetings 📅",
        subtitle=f"{meetings['day']} · {meetings['time']}",
        body_lines=[meetings["location"]],
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def _step_text(step: dict) -> str:
    """Render a join step, filling in the meeting details from one place.

    Step one used to spell out the day, time, and room a second time, which
    meant the room number lived in two hand-written copies that could drift.
    """
    if not step.get("prepend_meeting"):
        return step["text"]
    meetings = nsbe()["meetings"]
    return (
        f"{meetings['day']} {meetings['time']}, {meetings['location']} — "
        + step["text"].removeprefix("Come to a meeting — ")
    )


def join_message() -> ChatMessage:
    steps = nsbe()["join_steps"]
    contact = nsbe()["contact"]
    # Buttons that open the links, so nothing in the bubble gets unfurled.
    chips = [
        MenuButton(
            "✉️ Email them",
            {"action": "open_link", "link": "email"},
            primary=True,
            url=f"mailto:{contact['email']}",
        ),
        MenuButton(
            "📸 Instagram",
            {"action": "open_link", "link": "instagram"},
            url=_link("instagram")["url"],
        ),
        MenuButton(
            "🔗 All their links",
            {"action": "open_link", "link": "linktree"},
            url=_link("linktree")["url"],
        ),
    ]
    payload = build_chip_payload(
        title="How to join 🤝",
        subtitle="No membership needed to show up",
        body_lines=[_step_text(step) for step in steps],
        chips=chips,
        source=SOURCE,
        per_row=1,
        footer_buttons=[
            MenuButton("📅 When they meet", {"action": "topic", "topic": "meetings"}),
            MenuButton("↩️ Back", {"action": "topic", "topic": "home"}),
        ],
        footnote=(
            f"From their site and linktree, read {_checked('chapter_site')}."
        ),
    )
    return card_message("**How to join UCSC NSBE**", payload)


def about_message() -> ChatMessage:
    chapter = nsbe()["chapter"]
    payload = build_chip_payload(
        title="What NSBE is 🎯",
        subtitle=chapter["name"],
        body_lines=[
            f"Mission: “{chapter['mission']}”",
            chapter["about"],
            f"Part of {chapter['parent_organization']['name']}, and affiliated "
            f"with UCSC's {chapter['affiliation']['name']}.",
        ],
        chips=[
            MenuButton(
                "🌐 Chapter site",
                {"action": "open_link", "link": "site"},
                url=_link("site")["url"],
            ),
            MenuButton(
                "🏛️ National NSBE",
                {"action": "open_link", "link": "national"},
                url=_link("national")["url"],
            ),
        ],
        source=SOURCE,
        per_row=1,
        footer_buttons=[
            MenuButton("📅 When they meet", {"action": "topic", "topic": "meetings"}),
            MenuButton("🤝 How to join", {"action": "topic", "topic": "join"}),
            MenuButton("↩️ Back", {"action": "topic", "topic": "home"}),
        ],
        footnote=(
            "The mission is quoted from the chapter's own page, read "
            f"{_checked('chapter_site')}."
        ),
    )
    return card_message("**What NSBE is**", payload)


def links_message() -> ChatMessage:
    """Every link the chapter publishes, as buttons that open them.

    A link button rather than a URL in the bubble: message text gets unfurled
    into a preview card by the client, and six links would mean six of them.
    Each button carries its id as a selection too, so a client that ignores
    the url still sends the tap and gets the address back as text.
    """
    links = nsbe()["links"]
    chips = [
        MenuButton(
            f"{item['label']}",
            {"action": "open_link", "link": item["id"]},
            url=item["url"],
        )
        for item in links
    ]
    payload = build_chip_payload(
        title="Their links 🔗",
        subtitle="Everything the chapter publishes",
        body_lines=[f"{item['label']} — {item['why']}" for item in links],
        chips=chips,
        source=SOURCE,
        footer_buttons=[
            MenuButton("📅 When they meet", {"action": "topic", "topic": "meetings"}),
            MenuButton("↩️ Back", {"action": "topic", "topic": "home"}),
        ],
        per_row=1,
        footnote=f"Collected from their site and linktree, read {_checked('chapter_site')}.",
    )
    return card_message("**UCSC NSBE — their links**", payload)


def link_fallback_message(link_id: str) -> ChatMessage:
    """The address as text, for a client that ignored a link button."""
    if link_id == "email":
        contact = nsbe()["contact"]
        return create_text_chat(f"Email the chapter: {contact['email']}")
    try:
        item = _link(link_id)
    except StopIteration:
        return unknown_message()
    return create_text_chat(f"**{item['label']}** — {item['why']}\n{item['url']}")


def unknown_message() -> ChatMessage:
    """What to say when asked something the chapter has not published.

    This agent knows one organization from two pages. Board members, event
    dates, and dues are not on either, and making them up would be the exact
    failure the rest of this project exists to prevent — so it says so and
    points at the people who do know.
    """
    contact = nsbe()["contact"]
    preamble = (
        "I only know what UCSC NSBE publishes on their own pages — when they "
        "meet, what the chapter is, and how to reach them.\n\n"
        f"For anything else — officers, event dates, dues — ask them directly: "
        + link_row(
            ("Email", f"mailto:{contact['email']}"),
            ("Instagram", _link("instagram")["url"]),
        )
    )
    buttons = [
        MenuButton("📅 When they meet", {"action": "topic", "topic": "meetings"}, primary=True),
        MenuButton("🤝 How to join", {"action": "topic", "topic": "join"}),
        MenuButton("🎯 What NSBE is", {"action": "topic", "topic": "about"}),
        MenuButton("🔗 Their links", {"action": "topic", "topic": "links"}),
    ]
    return menu_message(
        preamble,
        title="Ask them directly 💬",
        subtitle="I don't hold what they haven't published",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def about_data_message() -> ChatMessage:
    """Where every fact came from, and what is deliberately missing."""
    meta = nsbe()["_meta"]
    lines = ["**Where this comes from**", ""]
    for entry in meta["sources"].values():
        lines.append(f"• {entry['url']} — read {entry['checked']}")
    lines.append("")
    lines.append(meta["staleness_warning"])
    lines.append("")
    lines.append(meta["not_recorded"])
    return create_text_chat("\n".join(lines))
