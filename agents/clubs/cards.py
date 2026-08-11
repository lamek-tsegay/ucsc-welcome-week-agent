"""Card and text rendering for the clubs agent."""

from __future__ import annotations

from agents.clubs.search import ScoredClub, category_label
from common.cards import (
    CardItem,
    DetailRow,
    MenuButton,
    build_detail_payload,
    build_list_payload,
    card_message,
    menu_message,
)
from common.chat import create_text_chat
from common.links import essentials_text
from common.loader import club_categories
from common.notices import (
    CLUBS_CONTACT,
    ENGINEERING_ORGS_URL,
    OFFICIAL_CLUBS_URL,
    badge,
    clubs_disclaimer,
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
    ("active", "🏃 Active & outdoors", "moving and exploring", {"sports", "fitness", "outdoors", "competition"}),
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
        "Tap **🎯 Match my vibe** and answer one question, or just tell me "
        "what you're into — *I like anime*, *something outdoorsy*, *pre-med "
        "stuff*.\n\n"
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


def vibe_picker_message() -> ChatMessage:
    """The one-question quiz. Six taps cover every kind of student."""
    preamble = (
        "**What's your vibe?** Tap the one that sounds most like you and I'll "
        "match you with organizations — no club names needed.\n\n"
        + "\n".join(f"• {label} — {blurb}" for _, label, blurb, _ in VIBES)
    )
    buttons = [
        MenuButton(label, {"action": "vibe_pick", "vibe": key})
        for key, label, _, _ in VIBES
    ]
    return menu_message(
        preamble,
        title="Match my vibe 🎯",
        subtitle="One tap — I'll do the matching",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
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
    """Every organization in one card — tap any one to pop its details open.

    This is the same shape as a normal search result (list_message): one card,
    every match as a tappable row, "Details" opens the detail card. The only
    difference is scope — all clubs instead of a filtered set — so browsing
    everything behaves exactly like browsing a category, just bigger. The vibe
    quiz rides along as footer buttons for narrowing down instead of scrolling.
    """
    ordered = sorted(all_clubs, key=lambda c: (c["category"], c["name"]))

    lines = [
        f"**Sure — here are all {len(ordered)} organizations I know** 🎓",
        "",
        "Tap any one below for details, or use a vibe to narrow the list down.",
        "",
        "_✅-marked engineering orgs are confirmed on the official Baskin "
        "page; the rest are representative examples. The official directories "
        "have far more._",
        "",
        clubs_disclaimer(),
    ]
    preamble = "\n".join(lines)

    items = [
        CardItem(
            record_id=club["id"],
            heading=_name_with_emoji(club),
            body=club["description"],
            badges=[
                (category_label(club["category"]), "info"),
                badge(club["verified"]),
            ],
            button_label="Details",
        )
        for club in ordered
    ]

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

    payload = build_list_payload(
        items,
        title=f"All {len(ordered)} organizations 🎓",
        subtitle="Tap one for details",
        id_field=CLUB_ID_FIELD,
        source=SOURCE,
        footer_buttons=footer,
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
    lines = [heading, ""]
    lines.extend(_summary_line(item.club) for item in scored)
    lines.append("")
    lines.append(clubs_disclaimer())
    preamble = "\n".join(lines)

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
    )
    return card_message(preamble, payload)


def detail_message(
    club: dict, others: list[dict], *, saved: bool = False
) -> ChatMessage:
    tags = ", ".join(sorted(club.get("tags", []))) or "—"

    website = club.get("website")

    rows = [
        DetailRow("Category", category_label(club["category"])),
        DetailRow("Interests", tags),
    ]
    if website:
        rows.append(DetailRow("Site", website))
    rows.append(
        DetailRow(
            "Contact",
            "See the club's site" if website else "See the official directory",
        )
    )
    rows.append(DetailRow("Meetings", "Not published here — check their site" if website else "Not published here — check the directory"))

    if club["verified"]:
        footnote = (
            "✅ Listed on the official Baskin Engineering student-organizations "
            f"page ({ENGINEERING_ORGS_URL}, checked "
            f"{club.get('source_checked', '2026')}). That page confirms the "
            "organization exists; check its own site for current details."
        )
    else:
        footnote = (
            "⚠️ Representative example, not a live roster entry. Registration status, "
            f"contact details, and meeting times live at {OFFICIAL_CLUBS_URL} "
            f"(or email {CLUBS_CONTACT})."
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
        footnote=footnote,
        back_label="Back to clubs",
        back_action=BACK_ACTION,
        source=SOURCE,
        extra_buttons=[
            MenuButton(
                "✅ On your shortlist" if saved else "⭐ Shortlist for Cornucopia",
                {CLUB_ID_FIELD: club["id"], "action": "save_club"},
            )
        ],
    )

    lines = [
        f"**{club['name']}** — {category_label(club['category'])}",
        "",
        club["description"],
        "",
        f"**Interests:** {tags}",
    ]
    if website:
        lines.append("")
        lines.append(f"**Site:** [{website}]({website})")
    lines.append("")
    lines.append("**How to actually join:**")
    if website:
        lines.append(f"• Their own site is the front door: {website}")
    lines.append(f"• Look it up in the official directory: {OFFICIAL_CLUBS_URL}")
    lines.append(
        "• Go to **Cornucopia** (Tue Sept 22, East Upper Field) — most "
        "organizations table there in person"
    )
    lines.append(f"• Or email SOAR at {CLUBS_CONTACT}")
    lines.append("")
    if club["verified"]:
        lines.append(
            "✅ *Confirmed: listed on the official Baskin Engineering "
            f"student-organizations page.* I still don't hold contact details "
            "or meeting times — their site is the authority."
        )
    else:
        lines.append(
            "⚠️ *This is a representative example, not a live roster entry.* I don't "
            "hold contact details or meeting times, because a wrong address would send "
            "you to the wrong place."
        )

    if others:
        lines.append("")
        lines.append(f"**Similar in {category_label(club['category'])}:**")
        lines.extend(f"• {other['name']}" for other in others)

    return card_message("\n".join(lines), payload)


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
    lines = ["**Your Cornucopia shortlist** ⭐", ""]
    lines.extend(_summary_line(club) for club in chosen)
    lines.append("")
    lines.append(
        "Find them in person at **Cornucopia** — Tuesday Sept 22, East Upper "
        "Field — or look them up in the official directory."
    )
    lines.append("")
    lines.append(clubs_disclaimer())

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
    )
    return card_message("\n".join(lines), payload)


def about_message() -> ChatMessage:
    """The full story: capabilities, categories, and the data-honesty rules."""
    return create_text_chat(welcome())


def links_message() -> ChatMessage:
    return create_text_chat(essentials_text())
