"""The ten residential colleges, as one shared registry.

Three different modules need to agree on what a college is: the events agent
filters by canonical college *name* ("Rachel Carson"), the navigation agent
routes from a college *landmark* ("rachel_carson_college"), and card buttons
need a stable *key* ("rachel_carson") that survives being serialised into a
selection payload. Keeping the three representations in one table means they
cannot drift, and a test pins every landmark id to data/landmarks.json.

Also home to `parse_home_declaration`: the "I'm at Porter" phrasing students
use to tell an agent where they live. Parsing it here keeps the phrase set
identical across agents; each agent resolves the extracted place its own way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class College:
    key: str  # stable id used inside card selections
    name: str  # canonical name, matches events' college filtering
    landmark_id: str  # navigation graph node, matches data/landmarks.json
    emoji: str  # cheap visual anchor for card buttons


COLLEGES: list[College] = [
    College("cowell", "Cowell", "cowell_college", "🌊"),
    College("stevenson", "Stevenson", "stevenson_college", "📚"),
    College("crown", "Crown", "crown_college", "👑"),
    College("merrill", "Merrill", "merrill_college", "🌍"),
    College("porter", "Porter", "porter_college", "🎨"),
    College("kresge", "Kresge", "kresge_college", "🌲"),
    College("oakes", "Oakes", "oakes_college", "🌅"),
    College("rachel_carson", "Rachel Carson", "rachel_carson_college", "🌱"),
    College("college_nine", "College Nine", "college_nine", "🤝"),
    College("john_r_lewis", "John R. Lewis", "john_r_lewis_college", "✊"),
]

_BY_KEY = {college.key: college for college in COLLEGES}
_BY_NAME = {college.name: college for college in COLLEGES}
_BY_LANDMARK = {college.landmark_id: college for college in COLLEGES}


def by_key(key: str | None) -> College | None:
    return _BY_KEY.get((key or "").strip().lower())


def by_name(name: str | None) -> College | None:
    return _BY_NAME.get((name or "").strip())


def by_landmark(landmark_id: str | None) -> College | None:
    return _BY_LANDMARK.get((landmark_id or "").strip())


# "I'm at Porter", "im in crown", "I live at Kresge", "my college is Oakes".
_HOME_RE = re.compile(
    r"^\s*(?:i\s*'?\s*m|i\s+am|i\s+live|my\s+college\s+is|i\s+stay)"
    r"\s*(?:at|in|from)?\s+(?P<place>.+?)\s*[.!]*\s*$",
    re.IGNORECASE,
)


def parse_home_declaration(text: str) -> str | None:
    """Extract the place from an "I'm at X" declaration, or None.

    Deliberately anchored to the whole message: "I'm at Porter" is a
    declaration, but "how do I get there, I'm at Porter" is a route question
    that the intent parsers already handle.
    """
    match = _HOME_RE.match(text or "")
    if not match:
        return None
    place = match.group("place").strip()
    # "I'm at a loss" style phrases: require something resolvable-looking.
    if not place or len(place) > 60:
        return None
    return place
