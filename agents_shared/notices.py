"""Verification labelling — the single implementation of the honesty rule.

Two of these agents describe real events at a real university on real dates,
built on curated seed data. A student who acts on a placeholder as though it were
the official schedule is worse off than one who got no answer. So:

- Anything with verified=false is labelled unofficial wherever it is shown.
- A confirmed event with an unpublished time says so; it never shows a guess.
- Every response carries a pointer to the authoritative source.

All three agents import from here rather than writing their own wording, so the
labelling cannot drift apart between them.
"""

from __future__ import annotations

from agents_shared.cards import BADGE_SUCCESS, BADGE_WARNING
from agents_shared.loader import campus

# Campus facts come from the pack (campuses/<CAMPUS_ID>/campus.yaml). Kept as
# module-level names because every call site treats them as constants; they
# are resolved once per process from whichever pack is active.
_OFFICIAL = campus()["official"]
OFFICIAL_EVENTS_URL = _OFFICIAL["events_url"]
OFFICIAL_CLUBS_URL = _OFFICIAL["clubs_directory_url"]
ENGINEERING_ORGS_URL = _OFFICIAL["engineering_orgs_url"]
CLUBS_CONTACT = _OFFICIAL["clubs_contact"]
TRANSIT_URL = _OFFICIAL["transit_url"]

FAIR = campus()["fair"]
FAIR_LINE = FAIR["line"]

UNVERIFIED_LABEL = "Unofficial"
VERIFIED_LABEL = "Confirmed"

TIME_UNPUBLISHED = "time not yet published"


def badge(verified: bool) -> tuple[str, str]:
    """Card badge marking a record's verification state."""
    if verified:
        return (VERIFIED_LABEL, BADGE_SUCCESS)
    return (UNVERIFIED_LABEL, BADGE_WARNING)


def marker(verified: bool) -> str:
    """Short inline prefix for text listings."""
    return "" if verified else "[unofficial] "


def event_time(time_value: str | None) -> str:
    """Render an event time, never inventing one."""
    return time_value if time_value else TIME_UNPUBLISHED


def events_disclaimer(*, any_unverified: bool) -> str:
    base = (
        f"Dates come from the official UCSC Slug Start page ({OFFICIAL_EVENTS_URL}). "
        "That page publishes dates but not times, and your college sends its own "
        "first-day schedule separately — check your email."
    )
    if any_unverified:
        base += (
            "\n\nEntries marked *unofficial* are placeholder examples in this agent's "
            "seed data, not announced events. Confirm anything marked unofficial "
            "before you plan around it."
        )
    return base


def clubs_footnote() -> str:
    """One-line caveat for the foot of a results card.

    The full `clubs_disclaimer()` is right for a detail view or a text-only
    client, but printed above every listing it buried the results. This keeps
    the two things a student must not lose — that entries are examples, and
    where the real roster lives — in a single muted line.
    """
    return (
        f"Examples, not a live roster · full directory: {OFFICIAL_CLUBS_URL} "
        f"· {CLUBS_CONTACT} · meet them at {FAIR['name']}, {FAIR['when']}"
    )


def events_footnote(*, any_unverified: bool) -> str:
    """One-line caveat for the foot of an events results card."""
    base = f"Dates from {OFFICIAL_EVENTS_URL} · times not published yet"
    if any_unverified:
        base += " · entries marked Unofficial are placeholder examples"
    return base + " · your college emails its own first-day schedule"


def clubs_disclaimer() -> str:
    return (
        "Entries marked **Confirmed** are listed on official UCSC pages "
        f"(engineering orgs: {ENGINEERING_ORGS_URL}). The rest are "
        "representative examples, not a live roster — UCSC's directory updates "
        f"weekly through fall. Confirm at {OFFICIAL_CLUBS_URL} "
        f"or email {CLUBS_CONTACT}. Contact details and meeting times are "
        "deliberately omitted here rather than guessed.\n\n"
        f"In person, {FAIR['name']} ({FAIR['when']}, {FAIR['where']}) is where most "
        "organizations table."
    )


def transit_disclaimer() -> str:
    return (
        "Bus options are approximate and unverified — route numbers and schedules "
        f"change. Check {TRANSIT_URL} for live times."
    )


def approximate_match_heading(query_text: str, count: int, noun: str) -> str:
    """Heading for results the keyword parser did not match.

    When nothing matched directly, ASI:One is asked to guess at the underlying
    interest. That guess is often useful and sometimes nonsense — "quantum basket
    weaving underwater" maps cheerfully to the hobby category. Asserting a
    category the student never asked for reads as a real match, so results
    reached this way say plainly that they are the nearest thing found rather
    than a match. Labelling relevance honestly is the same rule as labelling
    data honestly.
    """
    trimmed = " ".join((query_text or "").split())
    if len(trimmed) > 60:
        trimmed = trimmed[:57] + "..."
    label = f'**Closest matches for "{trimmed}"**' if trimmed else "**Closest matches**"
    return (
        f"{label} — {count} {noun}\n\n"
        "Nothing matched that directly, so these are the nearest interests I "
        "could find. They may not be what you meant."
    )


def route_estimate_note() -> str:
    return (
        "Walking times are estimates on a curated campus path map, not turn-by-turn "
        "navigation. Coordinates are approximate."
    )
