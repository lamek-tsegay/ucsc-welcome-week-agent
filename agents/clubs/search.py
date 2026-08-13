"""Club search and interest matching.

Three ways in, all supported by the same scorer:

- **Browse a category** — "show me cultural orgs"
- **Match an interest** — "I like anime and want to meet people"
- **Name lookup** — "surf club"

Matching is deterministic keyword and tag work. ASI:One maps vaguer phrasings to
tags in the service layer, but is never required.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from agents_shared.loader import club_categories, clubs

# Free-text interest words -> club tags. Deliberately broader than the events
# equivalent, since "I'm into X" phrasing varies more for organizations.
_INTEREST_TAGS: dict[str, set[str]] = {
    "anime": {"anime", "manga"},
    "manga": {"manga", "anime"},
    "cosplay": {"anime"},
    "game": {"games"},
    "games": {"games"},
    "gaming": {"gaming", "games", "esports"},
    "video game": {"gaming", "esports"},
    "esports": {"esports", "gaming"},
    "board game": {"board-games", "tabletop", "games"},
    "tabletop": {"tabletop", "board-games"},
    "dnd": {"ttrpg", "tabletop"},
    "d&d": {"ttrpg", "tabletop"},
    "rpg": {"ttrpg", "tabletop"},
    "code": {"programming", "tech"},
    "coding": {"programming", "tech"},
    "program": {"programming", "tech"},
    "software": {"programming", "tech"},
    "computer science": {"computer-science", "programming", "tech"},
    "cs": {"computer-science", "programming"},
    "tech": {"tech"},
    "ai": {"ai", "machine-learning", "tech"},
    "machine learning": {"machine-learning", "ai"},
    "robot": {"robotics", "engineering"},
    "robotics": {"robotics", "engineering"},
    "engineering": {"engineering", "tech"},
    "hackathon": {"hackathon", "tech"},
    "game dev": {"game-dev", "games", "programming"},
    "hike": {"hiking", "outdoors"},
    "hiking": {"hiking", "outdoors"},
    "backpack": {"hiking", "outdoors"},
    "outdoors": {"outdoors", "nature"},
    "outdoor": {"outdoors", "nature"},
    "nature": {"nature", "outdoors"},
    "surf": {"surfing", "ocean", "beach"},
    "surfing": {"surfing", "ocean"},
    "beach": {"beach", "ocean", "surfing"},
    "ocean": {"ocean", "marine"},
    "climb": {"climbing", "outdoors"},
    "climbing": {"climbing", "outdoors"},
    "bike": {"cycling", "outdoors"},
    "cycling": {"cycling", "outdoors"},
    "mountain bike": {"cycling", "outdoors"},
    "run": {"fitness", "sports"},
    "sport": {"sports", "fitness"},
    "sports": {"sports", "fitness"},
    "fitness": {"fitness", "sports"},
    "gym": {"fitness", "sports"},
    "frisbee": {"frisbee", "sports"},
    "ultimate": {"frisbee", "sports"},
    "martial art": {"martial-arts", "fitness"},
    "karate": {"martial-arts"},
    "music": {"music", "arts"},
    "sing": {"singing", "music"},
    "singing": {"singing", "music"},
    "choir": {"singing", "music"},
    "a cappella": {"singing", "music"},
    "band": {"music"},
    "radio": {"radio", "media", "music"},
    "dj": {"radio", "music"},
    "dance": {"dance", "performance"},
    "dancing": {"dance", "performance"},
    "theater": {"theater", "performance", "arts"},
    "theatre": {"theater", "performance", "arts"},
    "acting": {"theater", "performance"},
    "improv": {"comedy", "theater"},
    "comedy": {"comedy", "performance"},
    "art": {"art", "arts", "creative"},
    "drawing": {"art", "visual-arts"},
    "painting": {"art", "visual-arts"},
    "photography": {"photography", "media"},
    "write": {"writing", "creative"},
    "writing": {"writing", "creative"},
    "poetry": {"literature", "writing"},
    "journalism": {"journalism", "media", "writing"},
    "newspaper": {"journalism", "media"},
    "media": {"media"},
    "volunteer": {"volunteering", "service"},
    "volunteering": {"volunteering", "service"},
    "service": {"service", "community"},
    "tutor": {"education", "service"},
    "tutoring": {"education", "service"},
    "mentor": {"education", "community"},
    "activism": {"advocacy", "community"},
    "advocacy": {"advocacy"},
    "politics": {"politics", "advocacy"},
    "government": {"politics", "leadership"},
    "leadership": {"leadership"},
    "environment": {"environment", "sustainability", "outdoors"},
    "sustainability": {"sustainability", "environment"},
    "climate": {"environment", "sustainability", "advocacy"},
    "food": {"food", "cooking"},
    "cooking": {"cooking", "food"},
    "cook": {"cooking", "food"},
    "premed": {"premed", "health", "career"},
    "pre-med": {"premed", "health"},
    "medicine": {"premed", "health"},
    "doctor": {"premed", "health"},
    "health": {"health", "wellness"},
    "prelaw": {"law", "career"},
    "pre-law": {"law", "career"},
    "law": {"law", "debate"},
    "debate": {"debate", "public-speaking"},
    "public speaking": {"public-speaking", "debate"},
    "business": {"business", "career"},
    "finance": {"finance", "business"},
    "econ": {"business", "finance"},
    "economics": {"business", "finance"},
    "internship": {"career"},
    "career": {"career"},
    "job": {"career"},
    "research": {"research", "academic"},
    "psychology": {"psychology", "research"},
    "biology": {"science", "research"},
    "marine": {"marine", "science", "ocean"},
    "science": {"science", "research"},
    "cultural": {"cultural", "identity"},
    "culture": {"cultural"},
    "identity": {"identity", "community"},
    "black": {"cultural", "identity"},
    "latino": {"cultural", "identity"},
    "latinx": {"cultural", "identity"},
    "asian": {"cultural", "identity"},
    "indigenous": {"cultural", "identity"},
    "native": {"cultural", "identity"},
    "lgbtq": {"lgbtq", "identity"},
    "queer": {"lgbtq", "identity"},
    "trans": {"lgbtq", "identity"},
    "international": {"international", "community"},
    "first gen": {"support", "community"},
    "first-generation": {"support", "community"},
    "transfer": {"support", "community"},
    "religion": {"spiritual"},
    "religious": {"spiritual"},
    "faith": {"spiritual"},
    "spiritual": {"spiritual"},
    "meditation": {"meditation", "mindfulness", "wellness"},
    "mindfulness": {"mindfulness", "wellness"},
    "greek": {"greek", "social"},
    "fraternity": {"greek"},
    "sorority": {"greek"},
    "meet people": {"social", "community"},
    "friends": {"social", "community"},
    "social": {"social"},
    "community": {"community"},
    "mental health": {"wellness", "health"},
    "wellness": {"wellness"},
}

_CATEGORY_HINTS: dict[str, str] = {
    "cultural": "cultural_identity",
    "identity": "cultural_identity",
    "academic": "academic_professional",
    "professional": "academic_professional",
    "pre-professional": "academic_professional",
    "arts": "arts_performance",
    "performance": "arts_performance",
    "performing": "arts_performance",
    "media": "media_publication",
    "publication": "media_publication",
    "sport": "sports_recreation",
    "sports": "sports_recreation",
    "recreation": "sports_recreation",
    "service": "service_advocacy",
    "advocacy": "service_advocacy",
    "tech": "tech_engineering",
    "technology": "tech_engineering",
    "engineering": "tech_engineering",
    "spiritual": "spiritual",
    "religious": "spiritual",
    "greek": "greek",
    "fraternity": "greek",
    "sorority": "greek",
    "hobby": "special_interest",
    "hobbies": "special_interest",
    "special interest": "special_interest",
}

_STOPWORDS = {
    "i", "im", "a", "an", "the", "to", "of", "in", "on", "at", "is", "are", "and",
    "or", "for", "with", "me", "my", "want", "like", "love", "into", "show", "find",
    "any", "some", "looking", "look", "interested", "join", "club", "clubs", "org",
    "orgs", "organization", "organizations", "society", "societies", "group",
    "groups", "ucsc", "campus", "student", "students", "whats", "what", "there",
    "get", "new", "people", "meet",
    # Conversational filler seen in live traffic: "Hi tell me what clubs are at
    # UCSC" must not leave "tell" behind as a matching keyword.
    "hi", "hey", "hello", "tell", "give", "gimme", "please", "know", "need",
    "wanna", "sure", "thanks", "thank", "list", "about", "which", "have", "you",
    "can", "your", "yall", "here",
}

_PUNCT_RE = re.compile(r"[^a-z0-9 &'-]+")
_WS_RE = re.compile(r"\s+")


@dataclass
class ClubQuery:
    tags: set[str] = field(default_factory=set)
    category: str | None = None
    keywords: set[str] = field(default_factory=set)
    named: str | None = None
    browse_all: bool = False
    # True when tags/category came from the ASI:One fallback rather than a
    # direct keyword match, so the reply can say the results are guesses.
    approximate: bool = False


@dataclass
class ScoredClub:
    club: dict
    score: float
    reasons: list[str] = field(default_factory=list)


def normalise(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", lowered).strip()


def category_label(category_id: str) -> str:
    for entry in club_categories():
        if entry["id"] == category_id:
            return entry["label"]
    return category_id.replace("_", " ").title()


def _phrase_pattern(phrase: str) -> str:
    """Match a phrase as a whole word, tolerating a plural 's'.

    Students type "board games", not "board game", so a strict word boundary
    after the phrase would miss the obvious case.
    """
    return rf"(?<![a-z]){re.escape(phrase)}s?(?![a-z])"


def detect_tags(text: str) -> set[str]:
    lowered = normalise(text)
    tags: set[str] = set()
    for phrase, mapped in _INTEREST_TAGS.items():
        if re.search(_phrase_pattern(phrase), lowered):
            tags |= mapped
    return tags


def detect_category(text: str) -> str | None:
    lowered = normalise(text)
    for phrase in sorted(_CATEGORY_HINTS, key=len, reverse=True):
        if re.search(_phrase_pattern(phrase), lowered):
            return _CATEGORY_HINTS[phrase]
    return None


def _match_name(text: str) -> str | None:
    """Club id if the text names a club closely enough."""
    lowered = normalise(text)
    if not lowered:
        return None

    names = {normalise(club["name"]): club["id"] for club in clubs()}

    for name, club_id in names.items():
        if lowered == name:
            return club_id

    # Substring both ways: "surf club" vs "Surf Club", "the anime club at ucsc".
    for name, club_id in names.items():
        if len(name) >= 6 and (name in lowered or lowered in name):
            return club_id

    close = difflib.get_close_matches(lowered, list(names), n=1, cutoff=0.8)
    return names[close[0]] if close else None


def _keywords(text: str) -> set[str]:
    return {
        word
        for word in normalise(text).split()
        if word not in _STOPWORDS and len(word) > 2
    }


_BROWSE_RE = re.compile(
    r"\b(?:all|every|everything|list|browse|what(?:'s| is| are)?\s+(?:there|available)"
    r"|categories|what\s+kinds?)\b",
    re.IGNORECASE,
)


# The domain noun itself. "What clubs are at UCSC" carries no interest signal —
# the noun IS the request, and the right answer is a spread, not a shrug.
_DOMAIN_NOUN_RE = re.compile(
    r"\b(clubs?|orgs?|organizations?|societies)\b", re.IGNORECASE
)


def build_query(text: str) -> ClubQuery:
    query = ClubQuery(
        tags=detect_tags(text),
        category=detect_category(text),
        keywords=_keywords(text),
        named=_match_name(text),
        browse_all=bool(_BROWSE_RE.search(text or "")),
    )
    # A generic ask about clubs with no other signal is browse intent, even if
    # conversational filler left stray keywords behind. Observed live:
    # "@ucsc-clubs Hi tell me what clubs are at UCSC" must get the spread.
    if (
        not query.tags
        and not query.category
        and not query.named
        and _DOMAIN_NOUN_RE.search(text or "")
    ):
        query.browse_all = True
    return query


def select(query: ClubQuery, *, limit: int = 8) -> tuple[list[ScoredClub], int]:
    """Filter and rank clubs. Returns the top results and the total matched."""
    candidates: list[ScoredClub] = []

    for club in clubs():
        score = 0.0
        reasons: list[str] = []

        if query.named and club["id"] == query.named:
            score += 20.0
            reasons.append("name match")

        tags = set(club.get("tags", []))
        overlap = tags & query.tags
        if overlap:
            score += 3.0 * len(overlap)
            reasons.append("matches " + ", ".join(sorted(overlap)))

        if query.category and club["category"] == query.category:
            score += 4.0
            reasons.append(f"in {category_label(query.category)}")

        alias_text = " ".join(club.get("aliases", []))
        haystack = normalise(
            f"{club['name']} {alias_text} {club['description']} {' '.join(tags)}"
        )
        hits = {word for word in query.keywords if word in haystack}
        if hits:
            score += 1.5 * len(hits)
            reasons.append("mentions " + ", ".join(sorted(hits)))

        if score > 0:
            candidates.append(ScoredClub(club=club, score=score, reasons=reasons))

    if not candidates and (query.browse_all or not query.keywords):
        # Nothing specific asked for: offer a spread across categories rather
        # than the first N alphabetically.
        seen: set[str] = set()
        for club in clubs():
            if club["category"] in seen:
                continue
            seen.add(club["category"])
            candidates.append(
                ScoredClub(club=club, score=1.0, reasons=["one per category"])
            )

    # Relevance first, confirmed as the tie-breaker. This deliberately differs
    # from events, where confirmed-first is the primary key: event placeholders
    # are stand-ins for the same kind of thing, but a confirmed *engineering*
    # org must not outrank the actual cultural orgs on a cultural query just
    # because it is verified and happens to share an "identity" tag.
    candidates.sort(
        key=lambda scored: (
            -scored.score,
            not scored.club["verified"],
            scored.club["name"],
        )
    )
    return candidates[:limit], len(candidates)


def by_id(club_id: str) -> dict | None:
    for club in clubs():
        if club["id"] == club_id:
            return club
    return None


def similar(club: dict, *, limit: int = 3) -> list[dict]:
    """Other clubs in the same category."""
    return [
        other
        for other in clubs()
        if other["category"] == club["category"] and other["id"] != club["id"]
    ][:limit]
