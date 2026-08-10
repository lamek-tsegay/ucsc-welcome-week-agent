"""Turn what a student typed into a landmark id.

New students do not use official building names. They say "the bookstore",
"sci hill", "OPERS", "c10", or they misspell "Stevenson". Resolution runs in
three passes, cheapest first:

1. Exact match on name or a curated alias.
2. Substring match, longest alias first (so "porter dining" beats "porter").
3. Fuzzy match via difflib, to absorb typos.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from common.loader import events, landmarks

_PUNCT_RE = re.compile(r"[^a-z0-9 &/]+")
_WS_RE = re.compile(r"\s+")

# Words that carry no signal for matching and hurt substring precision.
_STOPWORDS = {
    "the", "a", "an", "at", "to", "from", "in", "on", "of", "is", "where",
    "how", "do", "i", "get", "go", "walk", "route", "directions", "way",
    "please", "me", "my", "building", "ucsc", "campus",
}

FUZZY_CUTOFF = 0.72


@dataclass(frozen=True)
class Match:
    landmark_id: str
    name: str
    confidence: float
    how: str  # "exact" | "substring" | "fuzzy"


def normalise(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", lowered).strip()


def _strip_stopwords(text: str) -> str:
    kept = [word for word in text.split() if word not in _STOPWORDS]
    return " ".join(kept) if kept else text


def _alias_index() -> list[tuple[str, str]]:
    """(normalised_alias, landmark_id), longest alias first."""
    pairs: list[tuple[str, str]] = []
    for landmark_id, entry in landmarks().items():
        pairs.append((normalise(entry["name"]), landmark_id))
        for alias in entry.get("aliases", []):
            pairs.append((normalise(alias), landmark_id))
        # The bare id is a useful alias too ("east_upper_field").
        pairs.append((normalise(landmark_id.replace("_", " ")), landmark_id))

    # Welcome Week event titles resolve to their venue: "how do I get to
    # Cornucopia" means East Upper Field. Students know event names before
    # they know building names, so this is the phrasing they actually use.
    # Only events with a published venue participate — an unpublished venue
    # stays unroutable rather than guessed.
    known = landmarks()
    for event in events():
        location_id = event.get("location_id")
        if location_id and location_id in known:
            pairs.append((normalise(event["title"]), location_id))

    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return pairs


def resolve(text: str) -> Match | None:
    """Best landmark for a phrase, or None."""
    cleaned = normalise(text)
    if not cleaned:
        return None

    index = _alias_index()

    for alias, landmark_id in index:
        if cleaned == alias:
            return Match(landmark_id, landmarks()[landmark_id]["name"], 1.0, "exact")

    stripped = _strip_stopwords(cleaned)
    for alias, landmark_id in index:
        # Require aliases of a useful length to avoid "a" matching everything.
        if len(alias) >= 4 and (alias in stripped or alias in cleaned):
            return Match(
                landmark_id, landmarks()[landmark_id]["name"], 0.85, "substring"
            )

    aliases = [alias for alias, _ in index]
    close = difflib.get_close_matches(stripped, aliases, n=1, cutoff=FUZZY_CUTOFF)
    if close:
        alias = close[0]
        landmark_id = next(lid for a, lid in index if a == alias)
        score = difflib.SequenceMatcher(None, stripped, alias).ratio()
        return Match(landmark_id, landmarks()[landmark_id]["name"], score, "fuzzy")

    return None


def suggest(text: str, limit: int = 4) -> list[str]:
    """Landmark names to offer when resolution fails."""
    cleaned = _strip_stopwords(normalise(text))
    index = _alias_index()
    aliases = [alias for alias, _ in index]
    close = difflib.get_close_matches(cleaned, aliases, n=limit * 2, cutoff=0.4)

    names: list[str] = []
    for alias in close:
        landmark_id = next(lid for a, lid in index if a == alias)
        name = landmarks()[landmark_id]["name"]
        if name not in names:
            names.append(name)
        if len(names) >= limit:
            break

    if not names:
        names = [
            landmarks()["quarry_plaza"]["name"],
            landmarks()["mchenry_library"]["name"],
            landmarks()["science_hill"]["name"],
            landmarks()["opers"]["name"],
        ][:limit]
    return names
