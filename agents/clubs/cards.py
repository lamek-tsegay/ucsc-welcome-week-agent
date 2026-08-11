"""Card and text rendering for the clubs agent."""

from __future__ import annotations

from agents.clubs.search import ScoredClub, category_label
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
        MenuButton("🗂️ Browse categories", {"action": "quick", "q": "what categories are there"}),
        MenuButton("🤝 How to meet clubs", {"action": "meet_clubs"}),
        MenuButton("⭐ My shortlist", {"action": "shortlist"}),
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
                "🗂️ Browse by category",
                {"action": "quick", "q": "what categories are there"},
            )
        )
    footer.append(MenuButton("📋 Show me all of them", {"action": "show_all"}))

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


def meet_clubs_message() -> ChatMessage:
    """The honest how-to-join answer, promoted to a first-class feature."""
    preamble = (
        "**How to actually meet clubs during Welcome Week** 🤝\n\n"
        "1. **Go to Cornucopia** — Tuesday Sept 22 on East Upper Field. It's "
        "the involvement festival where most organizations table in person. "
        "One afternoon, everyone in one place.\n"
        f"2. **Browse the official directory** — {OFFICIAL_CLUBS_URL} "
        "(updated weekly through fall as orgs re-register).\n"
        f"3. **Email SOAR** — {CLUBS_CONTACT}, the office that supports all "
        "student organizations.\n\n"
        "I can help you build a shortlist first — tap 🎯 or tell me what "
        "you're into, and walk into Cornucopia knowing who to look for.\n\n"
        "_For walking directions to East Upper Field, ask the **UCSC Campus "
        "Navigation** agent._"
    )
    buttons = [
        MenuButton("🎯 Match my vibe", {"action": "quiz"}, primary=True),
        MenuButton(
            "🗂️ Browse categories",
            {"action": "quick", "q": "what categories are there"},
        ),
    ]
    return menu_message(
        preamble,
        title="Meet clubs in person 🤝",
        subtitle="Cornucopia · Tue Sept 22 · East Upper Field",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def full_roster_message(all_clubs: list[dict]) -> ChatMessage:
    """Every organization as a small chip in one card — tap for details.

    A roster is a picker, not a reading list. Each club is just its name on a
    compact button, three to a row and grouped by category, so all 76 fit in
    one scannable card. Everything a chip can't hold — description, category,
    verification status, links, how to join — is exactly what the detail card
    shows when it is tapped.

    ✅ marks confirmed organizations inline, since chips carry no badges.
    """
    by_category: dict[str, list[dict]] = {}
    for club in all_clubs:
        by_category.setdefault(club["category"], []).append(club)

    preamble = (
        f"**Sure — here are all {len(all_clubs)} organizations I know** 🎓\n\n"
        "Tap any name for details, or pick a vibe at the bottom to narrow it "
        "down.\n\n"
        + link_row(("Official directory", OFFICIAL_CLUBS_URL))
    )

    # Category headers keep a long grid navigable. Rendered as body lines
    # between chip groups would break the row chunking, so the grid is built
    # category by category with a labelled group each.
    chips: list[MenuButton] = []
    for entry in club_categories():
        members = sorted(by_category.get(entry["id"], []), key=lambda c: c["name"])
        if not members:
            continue
        for club in members:
            tick = "✅ " if club["verified"] else ""
            chips.append(
                MenuButton(
                    f"{tick}{club['name']}",
                    {CLUB_ID_FIELD: club["id"]},
                )
            )

    footer = [
        MenuButton(label, {"action": "vibe_pick", "vibe": key})
        for key, label, _, _ in VIBES
    ]
    footer.append(
        MenuButton(
            "🗂️ Browse by category",
            {"action": "quick", "q": "what categories are there"},
        )
    )

    payload = build_chip_payload(
        title=f"All {len(all_clubs)} organizations 🎓",
        subtitle="Tap any name for details",
        body_lines=None,
        chips=chips,
        source=SOURCE,
        footer_buttons=footer,
        per_row=3,
        footnote="✅ = confirmed on the official Baskin Engineering page. "
        + clubs_footnote(),
    )
    return card_message(preamble, payload)


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
    # The text bubble is the heading plus the one link a student may want to
    # tap: card text is not clickable, so the directory link has to live here.
    preamble = heading + "\n\n" + link_row(
        ("Official directory", OFFICIAL_CLUBS_URL)
    )

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


def detail_message(
    club: dict, others: list[dict], *, saved: bool = False
) -> ChatMessage:
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
        extra_buttons=[
            MenuButton(
                "✅ Shortlisted" if saved else "⭐ Shortlist",
                {CLUB_ID_FIELD: club["id"], "action": "save_club"},
            )
        ],
    )

    # The card carries the detail; the bubble carries the title and the
    # tappable links, since card text is not clickable.
    pairs = []
    if website:
        pairs.append(("Their site", website))
    pairs.append(("Official directory", OFFICIAL_CLUBS_URL))
    pairs.append(("Email SOAR", f"mailto:{CLUBS_CONTACT}"))

    preamble = (
        f"**{club['name']}** — {category_label(club['category'])}\n\n"
        + link_row(*pairs)
    )
    return card_message(preamble, payload)


def categories_message() -> ChatMessage:
    lines = ["**UCSC student organization categories**", ""]
    lines.extend(f"• {entry['label']}" for entry in club_categories())
    lines.append("")
    lines.append(
        "Ask about any of these, or just tell me what you're into — "
        "*I like hiking and photography* works fine."
    )
    lines.append("")
    lines.append(clubs_disclaimer())

    buttons = [
        MenuButton(
            f"{CATEGORY_EMOJI.get(entry['id'], '')} {entry['label']}".strip(),
            {"action": "category", "category": entry["id"]},
        )
        for entry in club_categories()
    ]
    buttons.append(MenuButton("🎯 Match my vibe instead", {"action": "quiz"}))
    return menu_message(
        "\n".join(lines),
        title="Browse by category 🗂️",
        subtitle="Tap one to see its organizations",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
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
            "🗂️ Browse categories",
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


def shortlist_toggled_message(
    club: dict, *, saved: bool, total: int
) -> ChatMessage:
    """Confirmation after ⭐, with no card.

    Re-rendering the detail card here made a one-tap acknowledgement as heavy
    as a fresh answer, and repeated the card the student was already looking
    at. A sentence and a nudge is the whole job.
    """
    if saved:
        count = (
            "that's your first one"
            if total == 1
            else f"that's {total} saved"
        )
        text = (
            f"⭐ Added **{club['name']}** to your shortlist — {count}.\n\n"
            "Want to see more clubs? Tell me what you're into, or say "
            "*my shortlist* to review your picks."
        )
    else:
        remaining = (
            "your shortlist is empty now"
            if total == 0
            else f"{total} still saved"
        )
        text = (
            f"Removed **{club['name']}** from your shortlist — {remaining}.\n\n"
            "Want to see more clubs?"
        )
    return create_text_chat(text)


def stale_selection_message() -> ChatMessage:
    return create_text_chat(
        "I've lost track of that organization — ask me again and tap from the "
        "fresh list."
    )


def empty_shortlist_message() -> ChatMessage:
    """Shown when ⭐ My shortlist has nothing in it yet."""
    preamble = (
        "**Your shortlist is empty so far.** ⭐\n\n"
        "Tap any organization for details, then **⭐ Shortlist for "
        "Cornucopia** — walk into the involvement festival (Tue Sept 22, East "
        "Upper Field) knowing exactly who to look for."
    )
    buttons = [
        MenuButton("🎯 Match my vibe", {"action": "quiz"}, primary=True),
        MenuButton(
            "🗂️ Browse categories",
            {"action": "quick", "q": "what categories are there"},
        ),
    ]
    return menu_message(
        preamble,
        title="My shortlist ⭐",
        subtitle="Star organizations to find at Cornucopia",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def shortlist_message(chosen: list[dict]) -> ChatMessage:
    """The student's starred organizations — their Cornucopia hit-list."""
    lines = [
        f"**Your Cornucopia shortlist** ⭐ — {len(chosen)} starred",
        "",
        "Find them in person at **Cornucopia** — Tuesday Sept 22, East Upper "
        "Field.",
        "",
        link_row(("Official directory", OFFICIAL_CLUBS_URL)),
    ]

    items = [
        CardItem(
            record_id=club["id"],
            heading=club["name"],
            body=club["description"],
            badges=[
                (category_label(club["category"]), "info"),
                badge(club["verified"]),
            ],
            button_label="Details",
        )
        for club in chosen
    ]
    footer = [
        MenuButton("🎯 Add more", {"action": "quiz"}),
        MenuButton("🤝 How to meet them", {"action": "meet_clubs"}),
        MenuButton("🗑️ Clear shortlist", {"action": "clear_shortlist"}),
    ]
    payload = build_list_payload(
        items,
        title="Your Cornucopia shortlist ⭐",
        subtitle=f"{len(chosen)} starred · tap for details",
        id_field=CLUB_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer,
        footnote=clubs_footnote(),
    )
    return card_message("\n".join(lines), payload)


def about_message() -> ChatMessage:
    """The full story: capabilities, categories, and the data-honesty rules."""
    return create_text_chat(welcome())


def links_message() -> ChatMessage:
    return create_text_chat(essentials_text())
