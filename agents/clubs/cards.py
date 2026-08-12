"""Card and text rendering for the clubs agent."""

from __future__ import annotations

from agents.clubs.search import ScoredClub, by_id, category_label
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
from common.links import essentials_text, link_row
from common.loader import club_categories
from common.notices import (
    CLUBS_CONTACT,
    ENGINEERING_ORGS_URL,
    OFFICIAL_CLUBS_URL,
    badge,
    clubs_disclaimer,
    clubs_footnote,
    marker,
)
from uagents_core.contrib.protocols.chat import ChatMessage

# One emoji per category — visual anchors only, applied uniformly.
CATEGORY_EMOJI = {
    "cultural_identity": "🌍",
    "academic_professional": "📚",
    "arts_performance": "🎭",
    "media_publication": "📰",
    "sports_recreation": "🏅",
    "service_advocacy": "🤝",
    "tech_engineering": "💻",
    "spiritual": "🕊️",
    "greek": "🏛️",
    "special_interest": "🎲",
}


def _name_with_emoji(club: dict) -> str:
    emoji = CATEGORY_EMOJI.get(club.get("category", ""), "")
    return f"{emoji} {club['name']}".strip()


CLUB_ID_FIELD = "club_id"
SOURCE = "clubs_tab"
BACK_ACTION = "back_to_clubs"

# Selection keys this agent's buttons carry beyond the club id.
EXTRA_FIELDS = ("vibe", "category", "q")

# The vibe matcher: six moods a brand-new student can pick without knowing any
# club names. Tags must exist in data/clubs.json — a test enforces that every
# vibe matches at least one organization, so the quiz can never dead-end.
VIBES: list[tuple[str, str, str, set[str]]] = [
    ("creative", "🎨 Creative & artsy", "making things", {"arts", "music", "theater", "art", "writing", "performance", "creative", "media"}),
    # "competition" is deliberately absent: in this data it tags robotics,
    # rocketry, and competitive programming far more than anything athletic,
    # so including it surfaced Formula Slug under "Active & outdoors".
    ("active", "🏃 Active & outdoors", "moving and exploring", {"sports", "fitness", "outdoors", "hiking", "climbing", "surfing", "cycling"}),
    ("curious", "🧠 Curious & academic", "ideas and career", {"academic", "research", "science", "debate", "career", "leadership", "tech", "engineering", "programming"}),
    ("chill", "🎮 Chill & playful", "games and hanging out", {"games", "gaming", "social", "food"}),
    ("global", "🌍 Cultural & global", "community and identity", {"cultural", "identity", "international", "community"}),
    ("impact", "💪 Service & impact", "helping and advocacy", {"service", "advocacy", "support"}),
]

VIBE_TAGS = {key: tags for key, _, _, tags in VIBES}
VIBE_LABELS = {key: label for key, label, _, _ in VIBES}


def welcome() -> str:
    labels = ", ".join(entry["label"] for entry in club_categories())
    return (
        "Hi — I'm the **UCSC Clubs & Societies** agent, here to help you find "
        "student organizations during Slug Start (Sept 21–26).\n\n"
        "Tell me what you're into and I'll match you. Try:\n"
        "• *clubs about hiking*\n"
        "• *I'm into anime*\n"
        "• *show me cultural orgs*\n"
        "• *anything for pre-med students*\n"
        "• *what categories are there*\n\n"
        f"**Categories:** {labels}\n\n"
        "One important caveat: UCSC's directory updates weekly through fall, so my "
        "entries are **representative examples rather than a live roster**, and I "
        "don't store contact details or meeting times — I'd rather point you at the "
        "official directory than guess.\n\n"
        "For event listings, ask the **UCSC Welcome Week Events** agent. For "
        "directions, ask **UCSC Campus Navigation**."
    )


def short_welcome() -> str:
    return (
        "Hey! 👋 I'm your **clubs & orgs** matchmaker for Welcome Week.\n\n"
        "Ask me *\"I'd like to know about the clubs at UCSC\"* and I'll ask "
        "what you're into, then match you. Or skip ahead and tell me straight "
        "out — *I like anime*, *something outdoorsy*, *pre-med stuff*.\n\n"
        "_My entries are examples, not a live roster — I'll always say so, "
        "and point you at the official directory._"
    )


def welcome_message() -> ChatMessage:
    """Welcome menu with the zero-typing paths up front."""
    buttons = [
        MenuButton("🎯 Match my vibe", {"action": "quiz"}, primary=True),
        MenuButton("🗂️ Browse all UCSC clubs", {"action": "quick", "q": "what categories are there"}),
        MenuButton("🔗 Campus links", {"action": "links"}),
        MenuButton("ℹ️ About my data", {"action": "about"}),
    ]
    return menu_message(
        short_welcome(),
        title="UCSC Clubs & Societies 🎓",
        subtitle="Find your people — no club names required",
        body_lines=["New here? Tap 🎯 and answer one question."],
        buttons=buttons,
        source=SOURCE,
    )


def _interest_buttons() -> list[MenuButton]:
    return [
        MenuButton(label, {"action": "vibe_pick", "vibe": key})
        for key, label, _, _ in VIBES
    ]


def _interest_card(
    preamble: str, *, title: str, subtitle: str, include_categories: bool
) -> ChatMessage:
    """One interest per full-width row, with secondary actions below a rule."""
    footer = []
    if include_categories:
        footer.append(
            MenuButton(
                "🗂️ Browse all UCSC clubs",
                {"action": "quick", "q": "what categories are there"},
            )
        )

    payload = build_chip_payload(
        title=title,
        subtitle=subtitle,
        body_lines=None,
        chips=_interest_buttons(),
        source=SOURCE,
        footer_buttons=footer,
        per_row=1,
    )
    return card_message(preamble, payload)


def interests_message() -> ChatMessage:
    """The first reply to "tell me about clubs" — asks interests, not a dump.

    A brand-new student can't use a list of 76 names they've never heard of,
    but anyone can answer "what are you into?". So the opening move is the
    question, and the roster stays one tap away for the rare student who
    genuinely wants to read all of it.
    """
    # The options live only on the card — listing them here too made the agent
    # read as if it were saying everything twice. Clients that render no cards
    # still have a way through: the free-text invitation below.
    preamble = (
        "Happy to help you find your people at UCSC! 🎓\n\n"
        "**First — what are you into?** Tap one below, or just tell me in your "
        "own words — *I like anime*, *something outdoorsy*, *pre-med stuff* "
        "all work."
    )
    return _interest_card(
        preamble,
        title="What are you into? 🎓",
        subtitle="Tap one — I'll match you with organizations",
        include_categories=True,
    )


def vibe_picker_message() -> ChatMessage:
    """The same question, reached deliberately via 🎯 Match my vibe."""
    preamble = (
        "**What's your vibe?** Tap whichever sounds most like you — no club "
        "names needed. You can also just describe yourself in your own words."
    )
    return _interest_card(
        preamble,
        title="Match my vibe 🎯",
        subtitle="One tap — I'll do the matching",
        include_categories=False,
    )


def category_card(entry: dict, members: list[dict]) -> ChatMessage:
    """One category's organizations as compact name chips.

    This is what "browse by category" lands on. Chips rather than rich rows,
    so the whole category fits — Technology & Engineering has 35 and a
    description-per-row layout would be unusable.

    Names sort case-insensitively: plain sorting files "iGEM" after "Women in
    Science and Engineering", because lowercase follows uppercase in ASCII.
    """
    ordered = sorted(members, key=lambda c: c["name"].lower())
    chips = [
        MenuButton(
            f"{club['name']}{' ✅' if club['verified'] else ''}",
            {CLUB_ID_FIELD: club["id"]},
        )
        for club in ordered
    ]
    payload = build_chip_payload(
        title=f"{CATEGORY_EMOJI.get(entry['id'], '')} {entry['label']}".strip(),
        subtitle=f"{len(ordered)} · tap any name for details",
        body_lines=None,
        chips=chips,
        source=SOURCE,
        footer_buttons=[
            MenuButton("🗂️ Browse all UCSC clubs", {"action": "quick", "q": "what categories are there"}),
            MenuButton("🎯 Match my vibe", {"action": "quiz"}),
        ],
        # One per row so every button is the same width. Two to a row sized
        # each button to its own label, so a column of organizations came out
        # ragged — and club names vary from "iGEM" to "Society for the
        # Advancement of Chicanos and Native Americans in Science".
        per_row=1,
        # Chips carry no badges, so without this a card of unmarked names
        # would read as a confirmed roster.
        footnote="✅ = confirmed on an official UCSC page. " + clubs_footnote(),
    )
    return card_message("", payload)

def _summary_line(club: dict) -> str:
    return (
        f"• {marker(club['verified'])}**{_name_with_emoji(club)}** — "
        f"{category_label(club['category'])}"
    )


def list_message(
    scored: list[ScoredClub],
    *,
    heading: str,
    footer_buttons: list[MenuButton] | None = None,
) -> ChatMessage:
    # The bubble carries the heading as plain text, deliberately with no URL
    # in it: the chat client unfurls any link it finds into a preview card, and
    # on a listing that box is pure noise. The directory URL still rides on the
    # card footnote, readable and copyable; detail cards keep the tappable
    # version, where acting on it is the point.
    preamble = heading

    items = [
        CardItem(
            record_id=item.club["id"],
            heading=_name_with_emoji(item.club),
            body=item.club["description"],
            badges=[
                (category_label(item.club["category"]), "info"),
                badge(item.club["verified"]),
            ],
            button_label="Details",
        )
        for item in scored
    ]

    payload = build_list_payload(
        items,
        title=heading.replace("**", ""),
        subtitle="Tap an organization for details",
        id_field=CLUB_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer_buttons,
        footnote=clubs_footnote(),
    )
    return card_message(preamble, payload)


def detail_message(club: dict, others: list[dict]) -> ChatMessage:
    tags = ", ".join(sorted(club.get("tags", []))) or "—"

    website = club.get("website")

    rows = [DetailRow("Interests", tags)]
    if website:
        rows.append(DetailRow("Site", website))

    join_lines = []
    if website:
        join_lines.append(f"• Their site: {website}")
    join_lines.append(f"• Directory: {OFFICIAL_CLUBS_URL}")
    join_lines.append("• Cornucopia — Tue Sept 22, East Upper Field")
    join_lines.append(f"• Email SOAR: {CLUBS_CONTACT}")

    blocks = [DetailBlock("How to join", join_lines)]
    if others:
        blocks.append(
            DetailBlock(
                "Similar", [" · ".join(other["name"] for other in others)]
            )
        )

    if club["verified"]:
        footnote = (
            "✅ Confirmed on the official Baskin Engineering page "
            f"({club.get('source_checked', '2026')}). Meeting times and contacts "
            "live on the club's own site, not here."
        )
    else:
        footnote = (
            "⚠️ Representative example, not a live roster entry. Contact details "
            "and meeting times are omitted rather than guessed."
        )

    # Link buttons rather than a link row in the bubble: a URL in message text
    # gets unfurled into a preview card by the client, which is what pushed
    # these links out of the bubble in the first place. Each carries its
    # selection too, so a client that ignores the url still sends the tap back
    # and gets the address as text.
    link_buttons = []
    if website:
        link_buttons.append(
            MenuButton(
                "🌐 Their site",
                {CLUB_ID_FIELD: club["id"], "action": "open_site"},
                primary=True,
                url=website,
            )
        )
    link_buttons.append(
        MenuButton(
            "📂 Official directory",
            {"action": "open_directory"},
            url=OFFICIAL_CLUBS_URL,
        )
    )
    link_buttons.append(
        MenuButton(
            "✉️ Email SOAR",
            {"action": "open_email"},
            url=f"mailto:{CLUBS_CONTACT}",
        )
    )

    payload = build_detail_payload(
        title=club["name"],
        heading=club["name"],
        body=club["description"],
        badges=[
            (category_label(club["category"]), "info"),
            badge(club["verified"]),
        ],
        rows=rows,
        blocks=blocks,
        footnote=footnote,
        back_label="Back",
        back_action=BACK_ACTION,
        source=SOURCE,
        extra_buttons=link_buttons,
    )

    # No URL in the bubble at all now: the links are buttons on the card, so
    # nothing here for the client to unfurl into a preview box.
    return card_message(f"**{club['name']}**", payload)


def all_clubs_message(all_clubs: list[dict]) -> ChatMessage:
    """Every organization in one card, alphabetical, names left-aligned.

    A list rather than a grid of buttons, for one reason: a button centres its
    own label and the element schema exposes no way to change that, so a
    column of buttons puts every name at a different starting point. List
    headings are text, which the client left-aligns — so names line up down
    the card however long or short they are. Body and badges are left empty to
    keep each row to a name and its button.

    Sorting is on the club name only, case-insensitively, so neither the
    category emoji nor the confirmed tick drags entries out of order.
    """
    ordered = sorted(all_clubs, key=lambda c: c["name"].lower())
    items = [
        CardItem(
            record_id=club["id"],
            heading=f"{_name_with_emoji(club)}{' ✅' if club['verified'] else ''}",
            body="",
            badges=[],
            button_label="Details",
        )
        for club in ordered
    ]
    payload = build_list_payload(
        items,
        title=f"All {len(ordered)} UCSC clubs 🎓",
        subtitle="Alphabetical · tap any name for details",
        id_field=CLUB_ID_FIELD,
        source=SOURCE,
        footer_buttons=[MenuButton("🎯 Match my vibe instead", {"action": "quiz"})],
        footnote="✅ = confirmed on an official UCSC page. " + clubs_footnote(),
    )
    return card_message(
        "Tap any organization for details, or tell me what you're into — "
        "*I like hiking and photography* works fine.",
        payload,
    )

def no_matches_message(query_text: str) -> ChatMessage:
    labels = ", ".join(entry["label"] for entry in club_categories())
    preamble = (
        f"I couldn't match \"{query_text.strip()}\" to anything in my examples.\n\n"
        f"Try a broader interest — *music*, *outdoors*, *tech*, *service*, "
        f"*cultural* — or browse a category: {labels}.\n\n"
        f"My data is a small representative sample. The full directory "
        f"({OFFICIAL_CLUBS_URL}) has far more, and Cornucopia on Tue Sept 22 is "
        f"where everyone tables in person."
    )
    buttons = [
        MenuButton("🎯 Match my vibe", {"action": "quiz"}, primary=True),
        MenuButton(
            "🗂️ Browse all UCSC clubs",
            {"action": "quick", "q": "what categories are there"},
        ),
    ]
    return menu_message(
        preamble,
        title="Nothing matched — try these 🎓",
        subtitle=None,
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def link_fallback_message(action: str, selection: dict) -> ChatMessage:
    """The address as text, for a client that ignored a link button.

    Without this a tap on such a button would do nothing at all, which is the
    worst outcome of the three — worse than the preview box these buttons
    exist to avoid.
    """
    if action == "open_site":
        club = by_id(selection.get(CLUB_ID_FIELD, ""))
        website = (club or {}).get("website")
        if website:
            return create_text_chat(f"**{club['name']}** — {website}")
        return create_text_chat(
            f"That organization has no site of its own. The directory has "
            f"more: {OFFICIAL_CLUBS_URL}"
        )
    if action == "open_email":
        return create_text_chat(
            f"SOAR supports all student organizations — email {CLUBS_CONTACT}."
        )
    return create_text_chat(f"The official directory: {OFFICIAL_CLUBS_URL}")


def stale_selection_message() -> ChatMessage:
    return create_text_chat(
        "I've lost track of that organization — ask me again and tap from the "
        "fresh list."
    )


def about_message() -> ChatMessage:
    """The full story: capabilities, categories, and the data-honesty rules."""
    return create_text_chat(welcome())


def links_message() -> ChatMessage:
    return create_text_chat(essentials_text())
