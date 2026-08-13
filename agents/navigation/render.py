"""Text rendering for the navigation agent.

Navigation replies are plain formatted text rather than cards: turn-by-turn steps
read better as a numbered list, and text works in any client.

Every distance and duration is presented as an estimate, because that is what it
is — a curated path map, not survey data.
"""

from __future__ import annotations

from agents.navigation.parse import NavIntent
from agents.navigation.router import Constraints, Route, TransitOption
from agents_shared.links import (
    accessibility_link_line,
    dining_link_line,
    transit_link_lines,
)
from agents_shared.loader import landmark_name, landmarks
from agents_shared.maps import PIN_CAVEAT, pin_line, walking_line
from agents_shared.notices import route_estimate_note, transit_disclaimer

WELCOME = (
    "Hi — I'm the **UCSC Campus Navigation** agent for Slug Start "
    "(Sept 21–26).\n\n"
    "Ask me things like:\n"
    "• *how do I get from Porter to McHenry Library*\n"
    "• *where is Quarry Plaza*\n"
    "• *route from Oakes to Science Hill avoiding hills*\n"
    "• *what's near Crown College*\n\n"
    "I know the ten colleges, the libraries, Science Hill, the dining halls, "
    "OPERS, and the Welcome Week venues. If you want events or clubs instead, "
    "ask the **UCSC Welcome Week Events** or **UCSC Clubs & Societies** agents."
)


def _elevation_phrase(route: Route) -> str:
    parts = []
    if route.total_climb_ft >= 25:
        parts.append(f"climb about {route.total_climb_ft} ft")
    if route.total_descent_ft >= 25:
        parts.append(f"descend about {route.total_descent_ft} ft")
    if not parts:
        return "Mostly level."
    return "You'll " + " and ".join(parts) + "."


# (upper-bound climb ft, meter, label) — tuned to this campus, where 300 ft is
# a real hike. The meter answers the question a map can't: "how hard is this?"
_EFFORT_SCALE = [
    (25, "▁▁▁▁▁", "flat"),
    (100, "▲▁▁▁▁", "easy"),
    (200, "▲▲▁▁▁", "moderate"),
    (300, "▲▲▲▁▁", "a solid climb"),
    (450, "▲▲▲▲▁", "tough"),
    (float("inf"), "▲▲▲▲▲", "leg day"),
]


def effort_meter(climb_ft: int) -> str:
    """One-line effort readout: `▲▲▲▁▁ a solid climb (210 ft up)`."""
    for ceiling, meter, label in _EFFORT_SCALE:
        if climb_ft < ceiling:
            if climb_ft < 25:
                return f"{meter} {label}"
            return f"{meter} {label} ({climb_ft} ft up)"
    raise AssertionError("unreachable")


def _flag_notes(
    route: Route, constraints: Constraints, *, transit_available: bool
) -> list[str]:
    notes: list[str] = []
    flags = route.flags_present

    if route.relaxed_flags:
        readable = {"steep": "steep sections", "stairs": "stairs"}
        named = ", ".join(readable.get(flag, flag) for flag in route.relaxed_flags)
        message = f"⚠️ There's no route between these two that avoids {named}."
        # Only point at a bus if there actually is one below.
        if transit_available:
            message += " This is the best walking option — consider the bus below."
        else:
            message += (
                " This is the best walking option, and I don't have a single-bus "
                "ride between these two either."
            )
        notes.append(message)
    else:
        if "steep" in flags and not constraints.avoid_hills:
            notes.append(
                "⛰️ This route has a real climb. Ask me to *avoid hills* for a "
                "gentler option."
            )
        if "stairs" in flags and not constraints.accessible:
            notes.append(
                "🪜 Includes stairs. Ask for a *step-free* route if you need one."
            )

    if constraints.at_night:
        if "unlit" in flags:
            notes.append(
                "🌙 Parts of this are poorly lit after dark. Campus paths run through "
                "forest — bring a light and consider walking with someone."
            )
        else:
            notes.append("🌙 This route sticks to better-lit areas.")
        notes.append(
            "_Lighting notes are hand-curated approximations, not a safety audit._"
        )

    if "offcampus" in flags:
        notes.append("🚌 This leaves campus — the bus is almost always the better call.")
    if "bus_strongly_recommended" in flags:
        notes.append("❗ Walking this is a long haul. Take the bus.")

    if constraints.accessible:
        notes.append(
            "♿ Accessibility flags in my data are incomplete. Verify a step-free "
            "route with the Disability Resource Center before relying on it."
        )
    return notes


def render_transit(transit: TransitOption) -> str:
    lines = [
        f"🚌 **Bus alternative** — {transit.route_name}",
        f"Board at {transit.board_at}, ride {transit.stops} "
        f"stop{'s' if transit.stops != 1 else ''} (~{transit.minutes} min), "
        f"get off at {transit.alight_at}. No climbing.",
    ]
    if transit.note:
        lines.append(f"_{transit.note}_")
    lines.append(f"_{transit_disclaimer()}_")
    return "\n".join(lines)


def render_route(
    intent: NavIntent,
    route: Route,
    transit: TransitOption | None,
) -> str:
    origin_name = intent.origin.name if intent.origin else "your start"
    destination_name = intent.destination.name if intent.destination else "there"

    if route.is_trivial:
        return f"You're already at {destination_name}."

    header = (
        f"**{origin_name} → {destination_name}**\n"
        f"About **{route.total_minutes} min** on foot. {_elevation_phrase(route)}\n"
        f"Effort: {effort_meter(route.total_climb_ft)}"
    )

    lines = [header, ""]
    for index, step in enumerate(route.steps, start=1):
        detail = f"{index}. **{step.to_name}** — {step.minutes} min"
        if step.via:
            detail += f", via {step.via}"
        markers = []
        if step.elev_change_ft >= 40:
            markers.append(f"↑{step.elev_change_ft} ft")
        elif step.elev_change_ft <= -40:
            markers.append(f"↓{abs(step.elev_change_ft)} ft")
        if "steep" in step.flags:
            markers.append("steep")
        if "stairs" in step.flags:
            markers.append("stairs")
        if markers:
            detail += f" ({', '.join(markers)})"
        lines.append(detail)

    notes = _flag_notes(
        route, intent.constraints, transit_available=transit is not None
    )
    if notes:
        lines.append("")
        lines.extend(notes)

    if transit:
        lines.append("")
        lines.append(render_transit(transit))

    if intent.origin and intent.destination:
        maps_link = walking_line(
            intent.origin.landmark_id, intent.destination.landmark_id
        )
        if maps_link:
            lines.append("")
            lines.append(maps_link)

    if intent.constraints.accessible:
        lines.append(accessibility_link_line())

    lines.append("")
    lines.append(f"_{route_estimate_note()} {PIN_CAVEAT.strip('_')}_")
    return "\n".join(lines)


def _contextual_links(entry: dict) -> list[str]:
    """Official links that fit what this place is — a dining hall gets menus."""
    category = entry.get("category", "")
    if category == "dining":
        return [dining_link_line()]
    if category == "transit":
        return transit_link_lines()
    if category == "services" and "health" in entry.get("id", ""):
        return ["🩺 [Student Health Center](https://healthcenter.ucsc.edu)"]
    if category == "library":
        return ["📚 [Library hours & spaces](https://library.ucsc.edu)"]
    return []


def render_locate(landmark_id: str) -> str:
    entry = landmarks()[landmark_id]
    lines = [f"**{entry['name']}**"]

    if entry.get("notes"):
        lines.append(entry["notes"])

    facts = []
    if entry.get("college"):
        facts.append(f"Part of {entry['college']} College")
    if entry.get("elevation_ft") is not None:
        facts.append(f"roughly {entry['elevation_ft']} ft elevation")
    if facts:
        lines.append("")
        lines.append(" · ".join(facts) + ".")

    pin = pin_line(landmark_id)
    extras = _contextual_links(entry)
    if pin or extras:
        lines.append("")
        if pin:
            lines.append(pin)
        lines.extend(extras)

    lines.append("")
    lines.append(
        "Tell me where you're starting from and I'll give you walking directions "
        f"— for example *from Cowell to {entry['name']}*."
    )
    lines.append("")
    lines.append(PIN_CAVEAT if pin else
        "_Coordinates in my data are approximate, meant for relative positioning "
        "rather than precise geolocation._"
    )
    return "\n".join(lines)


def render_nearby(landmark_id: str, neighbours: list[tuple[str, int]]) -> str:
    name = landmark_name(landmark_id)
    if not neighbours:
        return f"I don't have anything mapped near {name}."

    lines = [f"**Closest to {name}** (walking estimates):", ""]
    lines.extend(f"• {place} — about {minutes} min" for place, minutes in neighbours)
    lines.append("")
    lines.append("Ask me for directions to any of these.")
    return "\n".join(lines)


def render_need_origin(destination_name: str) -> str:
    return (
        f"Happy to route you to **{destination_name}** — where are you starting from?\n\n"
        "Your college works fine (*Porter*, *Crown*, *Oakes*…), or a landmark like "
        "*Quarry Plaza* or *the Main Entrance*.\n\n"
        f"For example: *from Porter to {destination_name}*."
    )


def render_unresolved(query: str, suggestions: list[str]) -> str:
    lines = [
        f"I couldn't match \"{query.strip()}\" to a place I know."
    ]
    if suggestions:
        lines.append("")
        lines.append("Did you mean one of these?")
        lines.extend(f"• {name}" for name in suggestions)
    lines.append("")
    lines.append(
        "I cover the ten colleges, libraries, Science Hill, dining halls, OPERS, "
        "the Welcome Week venues, parking lots, and the main entrances."
    )
    return "\n".join(lines)


def render_unknown(query: str, suggestions: list[str]) -> str:
    lines = [
        "I'm not sure what you're asking for. I do three things:",
        "",
        "• **Directions** — *from Porter to McHenry Library*",
        "• **Locations** — *where is Quarry Plaza*",
        "• **What's nearby** — *what's near Crown College*",
    ]
    if query.strip() and suggestions:
        lines.append("")
        lines.append(f"If you meant a place, did you mean: {', '.join(suggestions)}?")
    return "\n".join(lines)


def render_no_route(origin_name: str, destination_name: str) -> str:
    return (
        f"I know both {origin_name} and {destination_name}, but I don't have a "
        "mapped path between them. My path data is a curated subset of campus, so "
        "this is a gap in my map rather than a gap in the sidewalks."
    )
