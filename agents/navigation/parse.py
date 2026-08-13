"""Intent parsing for navigation queries.

Deterministic patterns run first. They cover the overwhelming majority of real
phrasings ("from Porter to McHenry", "where is Quarry Plaza"), cost nothing, and
behave identically every run — which also makes them testable without a network.

ASI:One is the fallback for phrasings the patterns miss, not the primary path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.navigation.resolve import Match, resolve
from agents.navigation.router import Constraints
from agents_shared import asi1

KIND_ROUTE = "route"
KIND_LOCATE = "locate"
KIND_NEARBY = "nearby"
KIND_UNKNOWN = "unknown"


@dataclass
class NavIntent:
    kind: str
    origin: Match | None = None
    destination: Match | None = None
    constraints: Constraints = Constraints()
    origin_text: str = ""
    destination_text: str = ""
    source: str = "patterns"  # or "asi1"


_AVOID_HILLS_RE = re.compile(
    r"\b(?:avoid(?:ing)?|skip(?:ping)?|without|no|less|fewer|minimi[sz]e)\s+"
    r"(?:the\s+)?(?:big\s+|steep\s+)?(?:hills?|climbs?|climbing|steep|uphill|inclines?)"
    r"|\b(?:flat(?:test)?|gentler?|gentlest|easier|easiest)\s+(?:route|way|path|walk)"
    r"|\bnot\s+(?:too\s+)?steep\b"
    r"|\bless\s+steep\b",
    re.IGNORECASE,
)
_ACCESSIBLE_RE = re.compile(
    r"\b(?:wheelchair|accessible|accessibility|step[\s-]?free|stair[\s-]?free"
    r"|no\s+stairs|without\s+stairs|avoid(?:ing)?\s+stairs|mobility)\b",
    re.IGNORECASE,
)
_NIGHT_RE = re.compile(
    r"\b(at\s+night|after\s+dark|night[\s-]?time|late\s+at\s+night|well\s+lit|lit\s+route)\b",
    re.IGNORECASE,
)

_FROM_TO_RE = re.compile(
    r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destination>.+?)(?=$|[,.?!])", re.IGNORECASE
)
_X_TO_Y_RE = re.compile(
    r"^(?P<origin>[^,.?!]+?)\s+to\s+(?P<destination>[^,.?!]+?)$", re.IGNORECASE
)
_TO_ONLY_RE = re.compile(
    r"\b(?:get|go|walk|directions?|route|head|way)\s+(?:me\s+)?(?:to|toward|towards)\s+"
    r"(?P<destination>.+?)(?=$|[,.?!])",
    re.IGNORECASE,
)
_WHERE_IS_RE = re.compile(
    r"\bwhere(?:\s+is|'s|\s+are)?\s+(?:the\s+)?(?P<target>.+?)(?=$|[,.?!])",
    re.IGNORECASE,
)
_NEARBY_RE = re.compile(
    r"\b(?:what(?:'s| is)\s+)?(?:near|nearby|close\s+to|around)\s+(?:the\s+)?"
    r"(?P<target>.+?)(?=$|[,.?!])",
    re.IGNORECASE,
)

# Trailing constraint phrases must not be swallowed into a landmark name:
# "Science Hill avoiding hills" has to resolve to "Science Hill".
_TRAILING_NOISE_RE = re.compile(
    r"\s*\b(?:but\s+|and\s+|,\s*)?"
    r"(?:avoid(?:ing)?|skip(?:ping)?|without|no|minimi[sz]e|less|fewer)\s+"
    r"(?:the\s+)?(?:big\s+|steep\s+)?"
    r"(?:hills?|climbs?|climbing|steep|uphill|inclines?|stairs?|steps?)\b.*$",
    re.IGNORECASE,
)

# Standalone constraint words that can trail a place name.
_CONSTRAINT_WORDS_RE = re.compile(
    r"\s*\b(?:at\s+night|after\s+dark|night[\s-]?time"
    r"|step[\s-]?free|stair[\s-]?free|wheelchair(?:\s+accessible)?|accessible"
    r"|flat(?:test)?|gentler?|gentlest|easier|easiest)\b"
    r"(?:\s+(?:route|way|path|walk))?\s*",
    re.IGNORECASE,
)


def _constraints_from(text: str) -> Constraints:
    return Constraints(
        avoid_hills=bool(_AVOID_HILLS_RE.search(text)),
        accessible=bool(_ACCESSIBLE_RE.search(text)),
        at_night=bool(_NIGHT_RE.search(text)),
    )


def _clean_place(text: str) -> str:
    cleaned = _TRAILING_NOISE_RE.sub("", text or "")
    cleaned = _CONSTRAINT_WORDS_RE.sub(" ", cleaned)
    return cleaned.strip(" ,.?!")


def parse_patterns(text: str) -> NavIntent:
    """Deterministic parse. Always returns an intent, possibly KIND_UNKNOWN."""
    raw = (text or "").strip()
    constraints = _constraints_from(raw)

    match = _FROM_TO_RE.search(raw)
    if match:
        origin_text = _clean_place(match.group("origin"))
        destination_text = _clean_place(match.group("destination"))
        return NavIntent(
            kind=KIND_ROUTE,
            origin=resolve(origin_text),
            destination=resolve(destination_text),
            constraints=constraints,
            origin_text=origin_text,
            destination_text=destination_text,
        )

    match = _NEARBY_RE.search(raw)
    if match:
        target_text = _clean_place(match.group("target"))
        return NavIntent(
            kind=KIND_NEARBY,
            destination=resolve(target_text),
            constraints=constraints,
            destination_text=target_text,
        )

    match = _TO_ONLY_RE.search(raw)
    if match:
        destination_text = _clean_place(match.group("destination"))
        return NavIntent(
            kind=KIND_ROUTE,
            destination=resolve(destination_text),
            constraints=constraints,
            destination_text=destination_text,
        )

    match = _WHERE_IS_RE.search(raw)
    if match:
        target_text = _clean_place(match.group("target"))
        return NavIntent(
            kind=KIND_LOCATE,
            destination=resolve(target_text),
            constraints=constraints,
            destination_text=target_text,
        )

    match = _X_TO_Y_RE.match(raw)
    if match:
        origin_text = _clean_place(match.group("origin"))
        destination_text = _clean_place(match.group("destination"))
        return NavIntent(
            kind=KIND_ROUTE,
            origin=resolve(origin_text),
            destination=resolve(destination_text),
            constraints=constraints,
            origin_text=origin_text,
            destination_text=destination_text,
        )

    # Bare landmark name, e.g. "McHenry Library".
    direct = resolve(raw)
    if direct and direct.how in {"exact", "substring"}:
        return NavIntent(
            kind=KIND_LOCATE,
            destination=direct,
            constraints=constraints,
            destination_text=raw,
        )

    return NavIntent(kind=KIND_UNKNOWN, constraints=constraints, destination_text=raw)


_SYSTEM_PROMPT = """You extract navigation intent for a UC Santa Cruz campus \
navigation agent. Reply with a single JSON object and nothing else.

Schema:
{
  "kind": "route" | "locate" | "nearby" | "unknown",
  "origin": string or null,
  "destination": string or null,
  "avoid_hills": boolean,
  "accessible": boolean,
  "at_night": boolean
}

"route" means they want directions between two places. "locate" means they want
to know where one place is. "nearby" means they want what is close to a place.
Put place names in the user's own words; do not invent UCSC building names. If a
place is not mentioned, use null."""


async def parse_with_asi1(text: str) -> NavIntent | None:
    """LLM fallback. None if unavailable or unusable."""
    if not asi1.is_enabled():
        return None

    payload = await asi1.structured(system=_SYSTEM_PROMPT, user=text, max_tokens=200)
    if not payload:
        return None

    kind = payload.get("kind")
    if kind not in {KIND_ROUTE, KIND_LOCATE, KIND_NEARBY}:
        return None

    origin_text = payload.get("origin") or ""
    destination_text = payload.get("destination") or ""

    return NavIntent(
        kind=kind,
        origin=resolve(origin_text) if origin_text else None,
        destination=resolve(destination_text) if destination_text else None,
        constraints=Constraints(
            avoid_hills=bool(payload.get("avoid_hills")),
            accessible=bool(payload.get("accessible")),
            at_night=bool(payload.get("at_night")),
        ),
        origin_text=str(origin_text),
        destination_text=str(destination_text),
        source="asi1",
    )


def _is_actionable(intent: NavIntent) -> bool:
    if intent.kind == KIND_ROUTE:
        return intent.destination is not None
    if intent.kind in {KIND_LOCATE, KIND_NEARBY}:
        return intent.destination is not None
    return False


async def parse_intent(text: str) -> NavIntent:
    """Patterns first; ASI:One only when patterns come up short."""
    intent = parse_patterns(text)
    if _is_actionable(intent):
        return intent

    fallback = await parse_with_asi1(text)
    if fallback and _is_actionable(fallback):
        return fallback

    return intent
