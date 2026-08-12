"""Card rendering for the navigation agent.

Navigation was text-only. The text stays — turn-by-turn steps read best as a
numbered list, and text works in every client — but a card now rides alongside
it carrying the actions a new student would otherwise have to know to type:
one-tap reroutes (gentler / step-free / after dark / reverse), tap-to-walk from
a nearby list, and a college picker so "route me to X" needs no origin at all.

Selections this module emits (all JSON, all with source="nav_tab"):
    {"action": "set_home"}                       -> show the college picker
    {"action": "set_college", "college": key}    -> save home college
    {"action": "nearby_home"}                    -> what's near my college
    {"action": "route_to", "landmark_id": id}    -> walk from anchor/home to id
    {"action": "reroute", "mode": m}             -> rerun last route; m in
                                                    hills|stairs|night|reverse
    {"action": "quick", "q": text}               -> run a canned query
"""

from __future__ import annotations

from agents.navigation.router import Constraints, Route
from common.cards import (
    CardItem,
    MenuButton,
    build_list_payload,
    card_message,
    menu_message,
)
from common.colleges import COLLEGES
from common.chat import create_text_chat
from common.links import essentials_text
from uagents_core.contrib.protocols.chat import ChatMessage

SOURCE = "nav_tab"
LANDMARK_FIELD = "landmark_id"

# Selection keys this agent's buttons carry beyond the landmark id.
EXTRA_FIELDS = ("college", "mode", "q")


ABOUT_TEXT = (
    "**UCSC Campus Navigation** — the full story 🗺️\n\n"
    "UCSC is 2,000 acres of forested hillside; walking time is about elevation, "
    "not distance. I route with the hills in mind, give you an effort meter, "
    "flag stairs and poorly lit paths, and tell you when the bus is smarter.\n\n"
    "**Things I understand:**\n"
    "• *how do I get from Porter to McHenry Library*\n"
    "• *how do I get to Cornucopia* — event names work too\n"
    "• *route from Oakes to Science Hill avoiding hills*\n"
    "• *what's near Crown College* · *where is the gym*\n"
    "• *I'm at Kresge* — saves your college so *route to the bookstore* just works\n"
    "• *always step-free* — every route avoids stairs from then on\n\n"
    "**Honesty:** walking times and coordinates are hand-curated estimates, not "
    "survey data. Bus info is approximate — scmtd.com has live times. "
    "Accessibility flags are incomplete; verify with the Disability Resource "
    "Center.\n\n"
    "Events: **UCSC Welcome Week Events** · Orgs: **UCSC Clubs & Societies**"
)


def about_message() -> ChatMessage:
    return create_text_chat(ABOUT_TEXT)


def links_message() -> ChatMessage:
    return create_text_chat(essentials_text())


def welcome_message(home_name: str | None, *, step_free: bool = False) -> ChatMessage:
    """Welcome menu. Short and warm; the full pitch lives behind ℹ️."""
    preamble = (
        "Hey! 👋 I'm your **UCSC Campus Navigation** guide — walking routes "
        "that actually respect the hills.\n\n"
        "Say *\"I'm at Porter\"* once and *\"route to the library\"* just "
        "works. Event names work too: *\"how do I get to Cornucopia\"*.\n\n"
        "Also here: **UCSC Welcome Week Events** · **UCSC Clubs & Societies**"
    )

    step_free_label = "♿ Step-free: ON" if step_free else "♿ Always step-free"

    if home_name:
        body = [f"🏠 Your saved college: {home_name}"]
        if step_free:
            body.append("♿ Step-free routing is on for every route.")
        buttons = [
            MenuButton("📍 What's near me", {"action": "nearby_home"}, primary=True),
            MenuButton(
                "🧭 Example route",
                {"action": "quick", "q": "from Porter to McHenry Library"},
            ),
            MenuButton("🏠 Change my college", {"action": "set_home"}),
            MenuButton(step_free_label, {"action": "pref_stepfree"}),
            MenuButton("🔗 Campus links", {"action": "links"}),
            MenuButton("ℹ️ About", {"action": "about"}),
        ]
    else:
        body = ["Save your college once and every route can start from it."]
        buttons = [
            MenuButton("🏠 Set my college", {"action": "set_home"}, primary=True),
            MenuButton(
                "🧭 Example route",
                {"action": "quick", "q": "from Porter to McHenry Library"},
            ),
            MenuButton(
                "📍 Explore the map", {"action": "quick", "q": "where is Quarry Plaza"}
            ),
            MenuButton(step_free_label, {"action": "pref_stepfree"}),
            MenuButton("🔗 Campus links", {"action": "links"}),
            MenuButton("ℹ️ About", {"action": "about"}),
        ]

    return menu_message(
        preamble,
        title="UCSC Campus Navigation 🗺️",
        subtitle="Hills, stairs, and lighting accounted for",
        body_lines=body,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def step_free_toggled_message(now_on: bool) -> ChatMessage:
    """Confirmation for the step-free preference change."""
    if now_on:
        preamble = (
            "**Step-free routing is on.** ♿\n\n"
            "Every route I give you now avoids stairs and steep sections where "
            "a path exists, and tells you plainly when one doesn't. My "
            "accessibility flags are hand-curated and incomplete — please "
            "verify important routes with the Disability Resource Center.\n\n"
            "Tap the button again or say *step-free off* to turn it off."
        )
    else:
        preamble = (
            "**Step-free routing is off.** Routes go back to the fastest path, "
            "and you can still ask for a *step-free route* any time."
        )
    buttons = [
        MenuButton("♿ Step-free: ON" if now_on else "♿ Always step-free",
                   {"action": "pref_stepfree"}),
        MenuButton("🧭 Try a route", {"action": "quick", "q": "where is Quarry Plaza"}),
    ]
    return menu_message(
        preamble,
        title="Step-free preference ♿",
        subtitle="Applies to every route automatically",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def college_picker_message(*, note: str | None = None) -> ChatMessage:
    """Ten buttons, one per residential college."""
    preamble = (note + "\n\n" if note else "") + (
        "Which college are you in? Tap it and I'll remember it as your "
        "starting point.\n\n"
        "(You can change it any time — just say *I'm at Kresge*.)"
    )
    buttons = [
        MenuButton(
            f"{college.emoji} {college.name}",
            {"action": "set_college", "college": college.key},
        )
        for college in COLLEGES
    ]
    return menu_message(
        preamble,
        title="Set your college 🏠",
        subtitle="Used as your default starting point",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
        per_row=2,
    )


def route_message(
    preamble: str, *, route: Route, constraints: Constraints, reversible: bool
) -> ChatMessage:
    """The route text plus one-tap variants of the same journey.

    Buttons are offered only when they would change something: no "avoid hills"
    on an already-gentle route, no "step-free" when it is already step-free.
    """
    buttons: list[MenuButton] = []
    if route.has_steep and not constraints.avoid_hills:
        buttons.append(
            MenuButton("⛰️ Gentler route", {"action": "reroute", "mode": "hills"})
        )
    if route.has_stairs and not constraints.accessible:
        buttons.append(
            MenuButton("🪜 Step-free", {"action": "reroute", "mode": "stairs"})
        )
    if not constraints.at_night:
        buttons.append(
            MenuButton("🌙 After dark?", {"action": "reroute", "mode": "night"})
        )
    if reversible:
        buttons.append(
            MenuButton("🔄 Reverse", {"action": "reroute", "mode": "reverse"})
        )

    return menu_message(
        preamble,
        title="Your route 🗺️",
        subtitle="Tap to adjust without retyping",
        body_lines=[
            f"~{route.total_minutes} min · "
            f"↑{route.total_climb_ft} ft · ↓{route.total_descent_ft} ft"
        ],
        buttons=buttons,
        source=SOURCE,
    )


def nearby_message(
    preamble: str, neighbours: list[tuple[str, str, int]]
) -> ChatMessage:
    """Nearby list where every row is walkable in one tap.

    `neighbours` is (landmark_id, name, minutes).
    """
    items = [
        CardItem(
            record_id=landmark_id,
            heading=name,
            body=f"about {minutes} min on foot",
            badges=[],
            button_label="🚶 Walk there",
        )
        for landmark_id, name, minutes in neighbours
    ]
    payload = build_list_payload(
        items,
        title="Closest landmarks 📍",
        subtitle="Walking estimates — tap one for directions",
        id_field=LANDMARK_FIELD,
        source=SOURCE,
    )
    return card_message(preamble, payload)


def locate_message(
    preamble: str, *, landmark_id: str, name: str, has_home: bool
) -> ChatMessage:
    """Location info with a route-me-there shortcut."""
    buttons = [
        MenuButton(
            "🚶 Route me there",
            {"action": "route_to", "landmark_id": landmark_id},
            primary=True,
        ),
        MenuButton(
            "📍 What's nearby", {"action": "quick", "q": f"what's near {name}"}
        ),
    ]
    if not has_home:
        buttons.append(MenuButton("🏠 Set my college", {"action": "set_home"}))
    return menu_message(
        preamble,
        title=f"{name} 📌",
        subtitle=None,
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )


def home_saved_message(name: str, nearby_preamble: str) -> ChatMessage:
    """Confirmation after saving a college, with immediate next steps."""
    preamble = (
        f"Saved — you're at **{name}**. 🏠\n\n"
        "From now on, *\"route to the library\"* or *\"how far is Science "
        "Hill\"* starts from there automatically. Say *I'm at [college]* any "
        "time to change it.\n\n" + nearby_preamble
    )
    buttons = [
        MenuButton(
            "🧭 Route somewhere",
            {"action": "quick", "q": "where is Quarry Plaza"},
        ),
        MenuButton("🏠 Change college", {"action": "set_home"}),
    ]
    return menu_message(
        preamble,
        title="College saved 🏠",
        subtitle=f"Routes now start from {name}",
        body_lines=None,
        buttons=buttons,
        source=SOURCE,
    )
