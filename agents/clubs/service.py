"""Clubs query handling, independent of the agent transport."""

from __future__ import annotations

import re

from agents.clubs import cards
from agents.clubs.search import (
    ClubQuery,
    ScoredClub,
    build_query,
    by_id,
    category_label,
    detect_category,
    select,
    similar,
)
from agents.navigation.service import answer_sibling_query
from common import asi1
from common.cards import MenuButton
from common.loader import club_categories, clubs as clubs_data
from common.notices import approximate_match_heading
from uagents_core.contrib.protocols.chat import ChatMessage

WELCOME = cards.welcome()

# Words that mark a query as this agent's own, exempt from nav bridging.
OWN_DOMAIN_RE = re.compile(
    r"\b(clubs?|orgs?|organizations?|societies)\b", re.IGNORECASE
)


async def bridge_to_navigation(text: str) -> str | None:
    """Answer a navigation-shaped question typed at this agent, or None."""
    return await answer_sibling_query(text, own_domain=OWN_DOMAIN_RE)

_CATEGORIES_RE = re.compile(
    r"\b(?:categor(?:y|ies)|what\s+kinds?|what\s+types?|what\s+sorts?)\b",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = """You map a student's interests to tags for a UC Santa Cruz \
student-organization finder. Reply with a single JSON object and nothing else.

Schema:
{
  "tags": [string],
  "category": string or null
}

Categories: cultural_identity, academic_professional, arts_performance,
media_publication, sports_recreation, service_advocacy, tech_engineering,
spiritual, greek, special_interest.

Tags are free-form lowercase interest words such as: hiking, surfing, climbing,
cycling, music, singing, dance, theater, comedy, art, writing, journalism, radio,
games, anime, tabletop, esports, tech, programming, robotics, ai, science,
marine, research, premed, law, debate, business, finance, career, service,
volunteering, advocacy, environment, sustainability, cultural, identity, lgbtq,
international, spiritual, meditation, wellness, health, food, cooking, social,
community, leadership, greek, fitness, sports.

Return at most 6 tags, only ones clearly implied."""


async def _enrich_with_asi1(text: str, query: ClubQuery) -> ClubQuery:
    """Map vaguer phrasing to tags when the keyword pass found nothing."""
    if query.named or query.tags or query.category or not asi1.is_enabled():
        return query

    payload = await asi1.structured(system=_SYSTEM_PROMPT, user=text, max_tokens=180)
    if not payload:
        return query

    raw_tags = payload.get("tags")
    if isinstance(raw_tags, list):
        query.tags |= {
            tag.strip().lower()
            for tag in raw_tags
            if isinstance(tag, str) and tag.strip()
        }

    category = payload.get("category")
    if isinstance(category, str):
        query.category = detect_category(category) or query.category

    # Anything the model contributed is a guess at what was meant, not a match.
    query.approximate = bool(query.tags or query.category)
    return query


def _heading(
    query: ClubQuery, scored: list[ScoredClub], total: int, query_text: str = ""
) -> str:
    count = len(scored)
    noun = "organization" if count == 1 else "organizations"
    shown = f"{count} {noun}" if count == total else f"top {count} of {total} {noun}"

    # Results reached only via the ASI:One fallback are guesses, so they are not
    # presented as a category match.
    if query.approximate and not query.named:
        return approximate_match_heading(query_text, count, noun)

    if query.named:
        return f"**Found it** — {shown}"
    if query.category:
        return f"**{category_label(query.category)}** — {shown}"
    if query.tags:
        interests = ", ".join(sorted(query.tags)[:4])
        return f"**Matching {interests}** — {shown}"
    return (
        f"**Sure — here's a taste of UCSC's organizations** 🎓 — {shown}, "
        "one per category"
    )


def respond_to_vibe(vibe_key: str) -> tuple[ChatMessage, list[str]] | None:
    """Answer a vibe-quiz tap. None for an unknown vibe key.

    The quiz maps a mood to tags rather than a category, so matches can cross
    category lines — a "creative" student sees the radio station alongside the
    theater troupe.
    """
    tags = cards.VIBE_TAGS.get(vibe_key)
    if tags is None:
        return None
    scored, total = select(ClubQuery(tags=set(tags)))
    if not scored:
        return cards.no_matches_message(cards.VIBE_LABELS[vibe_key]), []

    label = cards.VIBE_LABELS[vibe_key]
    count = len(scored)
    noun = "organization" if count == 1 else "organizations"
    shown = f"{count} {noun}" if count == total else f"top {count} of {total} {noun}"
    heading = f"**Your {label} matches** — {shown}"

    footer = [
        MenuButton("🎯 Try another vibe", {"action": "quiz"}),
        MenuButton(
            "🗂️ Browse categories",
            {"action": "quick", "q": "what categories are there"},
        ),
    ]
    message = cards.list_message(scored, heading=heading, footer_buttons=footer)
    return message, [item.club["id"] for item in scored]


def respond_to_category(category_id: str) -> tuple[ChatMessage, list[str]] | None:
    """Answer a category-browse tap. None for an unknown category."""
    known = {entry["id"] for entry in club_categories()}
    if category_id not in known:
        return None
    label = category_label(category_id)
    scored, total = select(ClubQuery(category=category_id))
    if not scored:
        return cards.no_matches_message(label), []
    count = len(scored)
    noun = "organization" if count == 1 else "organizations"
    shown = f"{count} {noun}" if count == total else f"top {count} of {total} {noun}"
    footer = [
        MenuButton("🗂️ All categories", {"action": "quick", "q": "what categories are there"}),
        MenuButton("🎯 Match my vibe", {"action": "quiz"}),
    ]
    message = cards.list_message(
        scored, heading=f"**{label}** — {shown}", footer_buttons=footer
    )
    return message, [item.club["id"] for item in scored]


async def respond_to_query(text: str) -> tuple[ChatMessage, list[str]]:
    """Answer a free-text clubs query."""
    if _CATEGORIES_RE.search(text or ""):
        return cards.categories_message(), []

    query = build_query(text)

    # A generic ask ("Hi, I'd like to know about the clubs at UCSC") gets the
    # interests question first, not 76 names. A student who doesn't know what
    # they want can't use a roster, but everyone can answer "what are you
    # into?" — so the first reply narrows, and the picker keeps a "show me
    # everything" escape hatch for anyone who really does want the full list.
    if query.browse_all and not (query.tags or query.category or query.named):
        return cards.interests_message(), []

    query = await _enrich_with_asi1(text, query)

    scored, total = select(query)
    if not scored:
        return cards.no_matches_message(text), []

    message = cards.list_message(
        scored, heading=_heading(query, scored, total, text)
    )
    return message, [item.club["id"] for item in scored]


def respond_to_full_roster() -> tuple[ChatMessage, list[str]]:
    """Every organization as name chips — the escape hatch from the picker."""
    all_clubs = sorted(clubs_data(), key=lambda c: (c["category"], c["name"]))
    return (
        cards.full_roster_message(all_clubs),
        [club["id"] for club in all_clubs],
    )


def respond_to_selection(club_id: str) -> ChatMessage:
    """Answer a card tap."""
    club = by_id(club_id)
    if club is None:
        return cards.stale_selection_message()
    return cards.detail_message(club, similar(club))
