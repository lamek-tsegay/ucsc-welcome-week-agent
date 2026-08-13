"""Curated official links — the places students actually need to go online.

Every URL here is an official UCSC or transit-authority site on a stable,
top-level domain. Nothing scraped, nothing guessed, no third parties beyond
Google Maps (built in common/maps.py) and the county bus operator. If a link
here ever rots, it fails visibly in the browser — which is still better than
an invented phone number — but sticking to institutional domains keeps that
risk low.

One registry, shared by all three agents, so "🔗 Campus links" is the same
answer everywhere.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

# (emoji, label, url, one-line why)
ESSENTIALS: list[tuple[str, str, str, str]] = [
    (
        "🎪", "Slug Start / Welcome Week",
        "https://welcome.ucsc.edu/slug-life/fall-welcome-week/",
        "The official schedule — dates, and times once published",
    ),
    (
        "🗺️", "Official campus map",
        "https://maps.ucsc.edu",
        "Interactive map of every building",
    ),
    (
        "🍽️", "Dining halls & menus",
        "https://dining.ucsc.edu",
        "Hours, menus, and meal plan info",
    ),
    (
        "🚌", "Campus transit (TAPS)",
        "https://taps.ucsc.edu",
        "Campus shuttles, parking, bike info",
    ),
    (
        "🚍", "Santa Cruz Metro buses",
        "https://scmtd.com",
        "City buses — live schedules and routes",
    ),
    (
        "🤝", "Student org directory",
        "https://getinvolved.ucsc.edu/student-organizations/join/",
        "The real club roster, updated weekly in fall",
    ),
    (
        "🔧", "Engineering orgs (Baskin)",
        "https://undergrad.engineering.ucsc.edu/student-organizations/",
        "Official list of Baskin Engineering student organizations",
    ),
    (
        "📚", "Library",
        "https://library.ucsc.edu",
        "Hours, study spaces, research help",
    ),
    (
        "🩺", "Student Health Center",
        "https://healthcenter.ucsc.edu",
        "Medical care, counseling (CAPS)",
    ),
    (
        "♿", "Disability Resource Center",
        "https://drc.ucsc.edu",
        "Accessibility services and accommodations",
    ),
]


def gmail_compose(to: str, *, subject: str = "", body: str = "") -> str:
    """A Gmail compose URL, pre-addressed and pre-written.

    A `mailto:` is the obvious thing here, but a card button can only open an
    https address, and a mailto also lands on whatever desktop mail client the
    device has configured — often nothing, on a phone borrowed for orientation
    week. This opens Gmail in the browser with the address, subject, and a
    first draft already filled in, so sending it is one more tap.

    Students not on Gmail still get the address: the agent answers the tap
    with it as text, and it is in the compose window either way.
    """
    # safe="@" keeps the address legible in the URL rather than as %40 — Gmail
    # accepts both, and it means the address is still findable on the card for
    # anyone reading the payload or copying it out.
    params = urlencode(
        {"view": "cm", "fs": "1", "to": to, "su": subject, "body": body},
        safe="@",
        quote_via=quote,
    )
    return f"https://mail.google.com/mail/?{params}"


def link_row(*pairs: tuple[str, str]) -> str:
    """A compact row of markdown links: `[A](url) · [B](url)`.

    Card `text` elements render plain text — markdown in them is not
    clickable, which is why the reference implementation puts its one
    clickable link in the chat bubble instead. So anything a student should be
    able to tap goes through here, into the bubble, while the card keeps the
    URL in readable plain text.
    """
    return " · ".join(f"[{label}]({url})" for label, url in pairs if url)


def essentials_text() -> str:
    """The links hub as a markdown block."""
    lines = ["**Essential UCSC links** 🔗", ""]
    for emoji, label, url, why in ESSENTIALS:
        lines.append(f"{emoji} **[{label}]({url})** — {why}")
    lines.append("")
    lines.append("_All official UCSC / transit-authority sites._")
    return "\n".join(lines)


def dining_link_line() -> str:
    return "🍽️ [Dining halls, hours & menus](https://dining.ucsc.edu)"


def transit_link_lines() -> list[str]:
    return [
        "🚌 [Campus shuttles (TAPS)](https://taps.ucsc.edu)",
        "🚍 [Santa Cruz Metro — live schedules](https://scmtd.com)",
    ]


def accessibility_link_line() -> str:
    return "♿ [Disability Resource Center](https://drc.ucsc.edu)"
