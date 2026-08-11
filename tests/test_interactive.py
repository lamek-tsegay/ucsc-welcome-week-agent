"""The interactive layer: menus, one-tap actions, memory, and composition.

Everything here runs offline — conftest disables ASI:One — and exercises the
service layer, so no Agent is constructed and no port is bound.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from common.cards import MenuButton, build_menu_payload
from common.chat import parse_card_selection
from common.colleges import COLLEGES, by_key, by_name, parse_home_declaration
from common.loader import landmarks
from uagents_core.contrib.protocols.chat import MetadataContent, TextContent


def payload_of(message) -> dict | None:
    for item in message.content:
        if isinstance(item, MetadataContent):
            return json.loads(item.metadata["card_payload"])
    return None


def text_of(message) -> str:
    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def selections_of(payload: dict) -> list[dict]:
    """Every button selection in a card payload, in document order."""
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            selection = node.get("action", {})
            if isinstance(selection, dict) and "selection" in selection:
                found.append(selection["selection"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


# --- college registry ---------------------------------------------------------


def test_registry_covers_all_ten_colleges_with_real_landmarks():
    assert len(COLLEGES) == 10
    known = landmarks()
    for college in COLLEGES:
        assert college.landmark_id in known, college.key
    assert len({c.key for c in COLLEGES}) == 10
    assert len({c.name for c in COLLEGES}) == 10


def test_college_lookups():
    assert by_key("porter").name == "Porter"
    assert by_name("Rachel Carson").landmark_id == "rachel_carson_college"
    assert by_key("hogwarts") is None
    assert by_name("") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I'm at Porter", "Porter"),
        ("im in crown", "crown"),
        ("I am at Kresge College", "Kresge College"),
        ("my college is Oakes", "Oakes"),
        ("I live at Rachel Carson", "Rachel Carson"),
    ],
)
def test_home_declaration_parses(text, expected):
    assert parse_home_declaration(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "how do I get to Porter",  # a question, not a declaration
        "where is Crown",
        "what's happening Wednesday",
        "",
    ],
)
def test_home_declaration_rejects_non_declarations(text):
    assert parse_home_declaration(text) is None


# --- card builders ------------------------------------------------------------


def test_menu_buttons_carry_source_and_selection():
    payload = build_menu_payload(
        title="T",
        subtitle=None,
        body_lines=["hello"],
        buttons=[MenuButton("Go", {"action": "quick", "q": "x"})],
        source="test_tab",
    )
    selections = selections_of(payload)
    assert selections == [{"action": "quick", "q": "x", "source": "test_tab"}]


def test_menu_buttons_chunk_into_rows():
    buttons = [MenuButton(str(i), {"action": "a"}) for i in range(7)]
    payload = build_menu_payload(
        title="T", subtitle=None, body_lines=None, buttons=buttons,
        source="s", per_row=3,
    )
    rows = [
        child
        for child in payload["root"]["children"]
        if child.get("direction") == "row"
    ]
    assert [len(row["children"]) for row in rows] == [3, 3, 1]


# --- selection parsing --------------------------------------------------------


def test_parse_extra_fields_from_json():
    parsed = parse_card_selection(
        '{"action": "set_college", "college": "porter", "source": "nav_tab"}',
        id_field="landmark_id",
        extra_fields=("college", "mode", "q"),
    )
    assert parsed == {
        "action": "set_college", "college": "porter", "source": "nav_tab"
    }


def test_parse_json_embedded_in_prose():
    text = (
        'The user selected an option: {"event_id": "cornucopia", '
        '"action": "directions", "source": "events_tab"} — please handle it.'
    )
    parsed = parse_card_selection(
        text, id_field="event_id", extra_fields=("college", "date", "q")
    )
    assert parsed is not None
    assert parsed["event_id"] == "cornucopia"
    assert parsed["action"] == "directions"


def test_plain_directions_question_is_not_a_selection():
    """"directions" is an ordinary word; only JSON may carry that action."""
    parsed = parse_card_selection(
        "directions to Quarry Plaza please",
        id_field="event_id",
        extra_fields=("college", "date", "q"),
    )
    assert parsed is None or "action" not in parsed


def test_prose_set_college_still_recognised():
    parsed = parse_card_selection(
        "the user chose set_college with college porter",
        id_field="landmark_id",
        extra_fields=("college",),
    )
    assert parsed is not None
    assert parsed["action"] == "set_college"
    assert parsed["college"] == "porter"


# --- navigation: memory, reroutes, cards --------------------------------------


from agents.navigation.render import effort_meter
from agents.navigation.service import (
    respond as nav_respond,
    reroute,
    route_between,
    try_home_declaration,
)


def test_effort_meter_scales_with_climb():
    assert "flat" in effort_meter(0)
    assert "easy" in effort_meter(60)
    assert "moderate" in effort_meter(150)
    assert "▲▲▲▲▲" in effort_meter(600)
    # The bar never shows climb it doesn't have.
    assert "▲" not in effort_meter(10)


def test_home_declaration_resolves_to_college_landmark():
    resolved = try_home_declaration("I'm at Porter")
    assert resolved is not None
    landmark_id, name = resolved
    assert landmark_id == "porter_college"
    assert "Porter" in name


def test_route_uses_saved_home_as_default_origin():
    reply = asyncio.run(
        nav_respond("route to McHenry Library", home_id="porter_college")
    )
    assert reply.used_home
    assert reply.route_ctx is not None
    assert reply.route_ctx["origin_id"] == "porter_college"
    assert "saved college" in text_of(reply.message)


def test_route_without_home_asks_for_origin():
    reply = asyncio.run(nav_respond("route to McHenry Library"))
    assert not reply.used_home
    assert reply.route_ctx is None
    assert "where are you starting" in text_of(reply.message).lower()


def test_route_card_offers_conditional_reroutes():
    reply = asyncio.run(nav_respond("from Porter to McHenry Library"))
    payload = payload_of(reply.message)
    assert payload is not None
    actions = {
        (sel.get("action"), sel.get("mode")) for sel in selections_of(payload)
    }
    # This route has steep sections and stairs, so both escapes are offered.
    assert ("reroute", "hills") in actions
    assert ("reroute", "stairs") in actions
    assert ("reroute", "reverse") in actions


def test_reroute_reverse_swaps_endpoints():
    first = asyncio.run(nav_respond("from Porter to McHenry Library"))
    assert first.route_ctx is not None
    reversed_reply = reroute(first.route_ctx, "reverse")
    assert reversed_reply is not None
    assert reversed_reply.route_ctx["origin_id"] == first.route_ctx["dest_id"]
    assert reversed_reply.route_ctx["dest_id"] == first.route_ctx["origin_id"]


def test_reroute_adds_constraint_and_keeps_it_in_context():
    first = asyncio.run(nav_respond("from Porter to McHenry Library"))
    gentler = reroute(first.route_ctx, "hills")
    assert gentler is not None
    assert gentler.route_ctx["hills"] is True


def test_followup_constraint_reruns_last_route():
    first = asyncio.run(nav_respond("from Porter to McHenry Library"))
    followup = asyncio.run(
        nav_respond("what about at night?", last_route=first.route_ctx)
    )
    assert followup.route_ctx is not None
    assert followup.route_ctx["night"] is True
    assert "🌙" in text_of(followup.message)


def test_nearby_rows_are_tappable_landmarks():
    reply = asyncio.run(nav_respond("what's near Crown College"))
    payload = payload_of(reply.message)
    assert payload is not None
    ids = [
        sel["landmark_id"]
        for sel in selections_of(payload)
        if "landmark_id" in sel
    ]
    assert ids, "nearby card has no tappable rows"
    assert all(lid in landmarks() for lid in ids)
    assert reply.anchor_id == "crown_college"


def test_route_between_known_landmarks():
    reply = route_between("crown_college", "mchenry_library")
    assert reply is not None
    assert "min" in text_of(reply.message)
    assert route_between("crown_college", "narnia") is None


# --- events: planner and directions -------------------------------------------

from datetime import date

from agents.events.service import (
    directions_to_event,
    parse_plan_request,
    respond_to_plan,
)

IN_WEEK = date(2026, 9, 22)


def test_parse_plan_request_named_day():
    assert parse_plan_request("plan my Tuesday", today=IN_WEEK) == "2026-09-22"
    assert parse_plan_request("itinerary for wednesday", today=IN_WEEK) == "2026-09-23"


def test_parse_plan_request_bare_day_uses_today_inside_window():
    assert parse_plan_request("plan my day", today=IN_WEEK) == "2026-09-22"
    # Outside the window there is no honest "today" — ask instead.
    assert parse_plan_request("plan my day", today=date(2026, 8, 9)) is True


def test_parse_plan_request_ignores_normal_queries():
    assert parse_plan_request("what's happening Wednesday", today=IN_WEEK) is None


def test_planner_puts_confirmed_first_and_includes_walking_legs():
    message, shown_ids = asyncio.run(respond_to_plan("2026-09-21"))
    body = text_of(message)
    assert "menu, not a schedule" in body
    assert shown_ids, "planner returned no events"
    # Monday has two confirmed events; they must lead.
    assert shown_ids[0] in {"new_admit_class_photo", "late_night_athletics_rec"}
    assert shown_ids[1] in {"new_admit_class_photo", "late_night_athletics_rec"}
    assert "Getting between venues" in body
    assert "about" in body and "min" in body


def test_planner_never_invents_times():
    message, _ = asyncio.run(respond_to_plan("2026-09-21"))
    body = text_of(message)
    assert "time not yet published" in body
    # No clock times anywhere: the university has not published any.
    import re

    assert not re.search(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", body, re.IGNORECASE)


def test_directions_to_event_from_college():
    message = asyncio.run(directions_to_event("cornucopia", "Crown"))
    assert message is not None
    body = text_of(message)
    assert "Cornucopia" in body
    assert "min" in body
    assert "Crown" in body


def test_directions_refused_when_venue_unpublished():
    # Choose Your Own Slugventure has location_id null — no route, no guess.
    message = asyncio.run(directions_to_event("choose_your_own_slugventure", "Crown"))
    assert message is None


def test_unverified_event_directions_carry_the_placeholder_warning():
    message = asyncio.run(directions_to_event("ph_farm_tour", "Porter"))
    assert message is not None
    assert "placeholder" in text_of(message).lower()


def test_detail_card_directions_button_gated_on_known_venue():
    from agents.events.cards import detail_message
    from agents.events.recommend import by_id

    with_venue = detail_message(by_id("cornucopia"), [])
    actions = {
        sel.get("action") for sel in selections_of(payload_of(with_venue))
    }
    assert "directions" in actions

    without_venue = detail_message(by_id("choose_your_own_slugventure"), [])
    actions = {
        sel.get("action") for sel in selections_of(payload_of(without_venue))
    }
    assert "directions" not in actions


# --- clubs: vibe matcher ------------------------------------------------------

from agents.clubs.cards import VIBES, vibe_picker_message, welcome_message
from agents.clubs.service import respond_to_category, respond_to_vibe


@pytest.mark.parametrize("vibe_key", [key for key, _, _, _ in VIBES])
def test_every_vibe_matches_at_least_one_org(vibe_key):
    """The quiz can never dead-end: each mood maps to real tags in the data."""
    result = respond_to_vibe(vibe_key)
    assert result is not None
    _message, shown_ids = result
    assert shown_ids, f"vibe {vibe_key!r} matched nothing"


def test_unknown_vibe_returns_none():
    assert respond_to_vibe("goblin_mode") is None


def test_vibe_results_keep_unofficial_labels():
    message, _ = respond_to_vibe("creative")
    assert "[unofficial]" in text_of(message)


def test_category_browse_by_id():
    result = respond_to_category("arts_performance")
    assert result is not None
    message, shown_ids = result
    assert shown_ids
    assert "Arts & Performance" in text_of(message)
    assert respond_to_category("nonexistent") is None


def test_vibe_picker_offers_every_vibe():
    payload = payload_of(vibe_picker_message())
    vibes = {sel.get("vibe") for sel in selections_of(payload) if "vibe" in sel}
    assert vibes == {key for key, _, _, _ in VIBES}


def test_clubs_welcome_leads_with_the_quiz():
    payload = payload_of(welcome_message())
    actions = [sel.get("action") for sel in selections_of(payload)]
    assert "quiz" in actions


# --- shared profile -----------------------------------------------------------

from common import profile


def test_profile_roundtrip_and_sharing():
    """One store, three agents: what one learns, all know."""
    profile.set_college("agent1qstudent", "Porter")
    profile.set_accessible("agent1qstudent", True)
    assert profile.college("agent1qstudent") == "Porter"
    assert profile.accessible("agent1qstudent") is True
    # A different student is untouched.
    assert profile.college("agent1qother") is None
    assert profile.accessible("agent1qother") is False


def test_profile_toggle_saved_and_clear():
    sender = "agent1qstudent"
    assert profile.toggle_saved(sender, "plan", "cornucopia") is True
    assert profile.toggle_saved(sender, "plan", "boardwalk_frolic") is True
    assert profile.saved(sender, "plan") == ["cornucopia", "boardwalk_frolic"]
    # Toggling again removes.
    assert profile.toggle_saved(sender, "plan", "cornucopia") is False
    assert profile.saved(sender, "plan") == ["boardwalk_frolic"]
    profile.clear_saved(sender, "plan")
    assert profile.saved(sender, "plan") == []


def test_profile_survives_corrupt_file(tmp_path, monkeypatch):
    """A mangled profile file degrades to empty, never to a crash."""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("UCSC_PROFILE_PATH", str(path))
    assert profile.get("anyone") == {}
    profile.set_college("anyone", "Kresge")  # and it heals on next write
    assert profile.college("anyone") == "Kresge"


# --- navigation: step-free preference and event-name routing ------------------


def test_saved_step_free_preference_applies_to_every_route():
    reply = asyncio.run(
        nav_respond(
            "from Cowell to Science Hill",
            always_accessible=True,
        )
    )
    assert reply.route_ctx is not None
    assert reply.route_ctx["stairs"] is True
    assert "Disability Resource Center" in text_of(reply.message)


def test_event_names_resolve_to_their_venue():
    """"How do I get to Cornucopia" is the phrasing students actually use."""
    from agents.navigation.resolve import resolve

    match = resolve("Cornucopia")
    assert match is not None
    assert match.landmark_id == "east_upper_field"

    match = resolve("Boardwalk Frolic")
    assert match is not None
    assert match.landmark_id == "boardwalk"


def test_unpublished_venue_event_does_not_resolve():
    """An event with no published venue must stay unroutable."""
    from agents.navigation.resolve import resolve

    match = resolve("Choose Your Own Slugventure")
    assert match is None or match.how == "fuzzy"


# --- events: my plan ----------------------------------------------------------

from agents.events.service import respond_to_my_plan


def test_my_plan_groups_by_day_with_walk_legs():
    message, shown_ids = asyncio.run(
        respond_to_my_plan(
            ["late_night_athletics_rec", "cornucopia", "new_admit_class_photo"]
        )
    )
    body = text_of(message)
    # Chronological days, confirmed events, honest framing.
    assert "Monday Sep 21" in body and "Tuesday Sep 22" in body
    assert "your picks" in body
    # Monday's two venues get a walking leg.
    assert "East Upper Field" in body and "min" in body
    # Within Monday, order is data-honest (confirmed first) — both are
    # confirmed here, so both simply appear.
    assert set(shown_ids) == {
        "late_night_athletics_rec", "cornucopia", "new_admit_class_photo"
    }


def test_my_plan_empty_state_recovers_with_buttons():
    message, shown_ids = asyncio.run(respond_to_my_plan([]))
    assert shown_ids == []
    payload = payload_of(message)
    assert payload is not None
    actions = {sel.get("action") for sel in selections_of(payload)}
    assert "plan_day" in actions


def test_my_plan_skips_stale_ids():
    message, shown_ids = asyncio.run(
        respond_to_my_plan(["cornucopia", "deleted_event_id"])
    )
    assert shown_ids == ["cornucopia"]


def test_detail_card_star_button_reflects_saved_state():
    from agents.events.cards import detail_message
    from agents.events.recommend import by_id

    fresh = detail_message(by_id("cornucopia"), [], saved=False)
    saved = detail_message(by_id("cornucopia"), [], saved=True)
    # ensure_ascii=False keeps the emoji literal instead of ⭐ escapes.
    assert "⭐ Add to my plan" in json.dumps(payload_of(fresh), ensure_ascii=False)
    assert "✅ In your plan" in json.dumps(payload_of(saved), ensure_ascii=False)


# --- clubs: shortlist ---------------------------------------------------------

from agents.clubs.service import respond_to_shortlist


def test_shortlist_lists_saved_clubs_with_cornucopia_pointer():
    message, shown_ids = respond_to_shortlist(["c_anime", "c_hiking"])
    body = text_of(message)
    assert shown_ids == ["c_anime", "c_hiking"]
    assert "Cornucopia" in body
    assert "[unofficial]" in body  # labels survive into the shortlist


def test_shortlist_empty_state():
    message, shown_ids = respond_to_shortlist([])
    assert shown_ids == []
    actions = {sel.get("action") for sel in selections_of(payload_of(message))}
    assert "quiz" in actions


# --- menu recovery and emoji --------------------------------------------------

from common.chat import is_menu_request


@pytest.mark.parametrize(
    "text", ["help", "menu", "  HELP?! ", "hi", "start over", "what can you do"]
)
def test_menu_requests_recognised(text):
    assert is_menu_request(text)


@pytest.mark.parametrize(
    "text",
    ["help me get to Porter", "hi, what's on Wednesday", "menu of events?"],
)
def test_real_questions_are_not_menu_requests(text):
    assert not is_menu_request(text)


def test_event_tag_emoji_never_wrong():
    from agents.events.cards import tag_emoji

    assert tag_emoji(["food", "social"]) == "🍕"
    assert tag_emoji(["completely_unknown_tag"]) == ""
    assert tag_emoji([]) == ""


def test_every_club_category_has_an_emoji():
    from agents.clubs.cards import CATEGORY_EMOJI
    from common.loader import club_categories

    for entry in club_categories():
        assert entry["id"] in CATEGORY_EMOJI, entry["id"]


# --- maps and links -----------------------------------------------------------

from common.maps import pin_url, walking_url, PIN_CAVEAT
from common.links import ESSENTIALS, essentials_text


def test_pin_url_built_from_real_coordinates():
    url = pin_url("quarry_plaza")
    assert url is not None
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "36." in url and "-122." in url  # Santa Cruz, not Null Island
    assert pin_url("narnia") is None


def test_walking_url_carries_both_endpoints_and_mode():
    url = walking_url("porter_college", "mchenry_library")
    assert url is not None
    assert "travelmode=walking" in url
    assert "origin=" in url and "destination=" in url
    assert walking_url("porter_college", "narnia") is None


def test_every_essential_link_is_institutional():
    """Only official UCSC / transit domains — no third parties to rot or mislead."""
    allowed = ("ucsc.edu", "scmtd.com")
    for _emoji, _label, url, _why in ESSENTIALS:
        assert url.startswith("https://"), url
        assert any(domain in url for domain in allowed), url
    text = essentials_text()
    assert "official" in text.lower()


def test_route_reply_includes_maps_link_and_caveat():
    reply = asyncio.run(nav_respond("from Porter to McHenry Library"))
    body = text_of(reply.message)
    assert "google.com/maps/dir" in body
    assert "travelmode=walking" in body
    assert "approximate" in body  # the pin caveat rides along


def test_locate_reply_includes_pin_and_contextual_links():
    reply = asyncio.run(nav_respond("where is Quarry Plaza"))
    body = text_of(reply.message)
    assert "google.com/maps/search" in body

    # A dining hall gets the menus link, because that's what you want next.
    dining = asyncio.run(nav_respond("where is Crown/Merrill Dining Hall"))
    assert "dining.ucsc.edu" in text_of(dining.message)


def test_event_detail_includes_venue_pin():
    from agents.events.cards import detail_message
    from agents.events.recommend import by_id

    message = detail_message(by_id("cornucopia"), [])
    body = text_of(message)
    assert "google.com/maps/search" in body
    assert "approximate" in body

    # No venue -> no pin, no pretend link.
    hidden = detail_message(by_id("choose_your_own_slugventure"), [])
    assert "google.com/maps" not in text_of(hidden)


# --- cross-agent bridging -----------------------------------------------------


def test_bridge_answers_nav_questions_but_not_domain_queries():
    """"any events for Crown students" must stay an events query."""
    from agents.events.service import bridge_to_navigation

    hijack = asyncio.run(bridge_to_navigation("any events for Crown students"))
    assert hijack is None

    genuine = asyncio.run(bridge_to_navigation("where is Quarry Plaza"))
    assert genuine is not None
    assert "Quarry Plaza" in genuine
    assert "Campus Navigation" in genuine  # credits the sibling


def test_clubs_domain_gate():
    from agents.clubs.service import bridge_to_navigation

    answered = asyncio.run(bridge_to_navigation("how do I get to the bookstore"))
    assert answered is not None
    stays_clubs = asyncio.run(bridge_to_navigation("clubs near Porter"))
    assert stays_clubs is None


def test_events_bridge_teaser_is_confirmed_only():
    from agents.navigation.service import events_pointer

    bridge = events_pointer("what's happening this week?")
    assert bridge is not None
    assert "Welcome Week Events" in bridge
    # Teaser lines must be confirmed events only — never placeholders.
    assert "unofficial" not in bridge.lower()

    # A route question mentioning an event name is NOT bridged away.
    assert events_pointer("how do I get to Cornucopia") is None


# --- short welcomes stay honest ----------------------------------------------


def test_short_welcomes_keep_a_data_honesty_line():
    from agents.events.cards import short_welcome
    from agents.clubs.cards import short_welcome as clubs_short

    assert "labelled" in short_welcome(None)
    assert "examples" in clubs_short()


def test_nav_welcome_keeps_sibling_references():
    from agents.navigation.cards import welcome_message

    body = text_of(welcome_message(None))
    assert "Campus Navigation" in body
    assert "Events" in body and "Clubs" in body


# --- live-traffic regression: mention prefixes and generic asks ---------------
# On 2026-08-09 a real ASI:One message arrived as
# "@ucsc-clubs Hi tell me what clubs are at UCSC" and got a no-match reply.
# Two separate defects: the mention handle survived into keyword matching, and
# conversational filler ("tell") wasn't stopworded, which disabled the
# no-keywords spread fallback.

from common.chat import strip_mention


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@ucsc-clubs Hi tell me what clubs are at UCSC",
         "Hi tell me what clubs are at UCSC"),
        ("@ucsc-clubs, hello", "hello"),
        ("@agent1 @agent2 hi", "hi"),
        ("no mention here", "no mention here"),
        ("email me @ midnight", "email me @ midnight"),  # not a leading mention
    ],
)
def test_strip_mention(raw, expected):
    assert strip_mention(raw) == expected


def _card_buttons(payload: dict) -> list[dict]:
    """Every button node in a card payload, in document order."""
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "button":
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def test_the_exact_live_failure_now_gets_the_full_roster():
    """The original bug report: "@ucsc-clubs Hi tell me what clubs are at
    UCSC" got a no-match reply. Fixed in stages — the query matches now, and
    the answer is a single card holding every club as a small name chip, with
    the detail card carrying everything a chip can't.
    """
    from agents.clubs.service import respond_to_query
    from common.loader import clubs as clubs_data

    # After the agent strips the mention, the service sees this:
    message, shown_ids = asyncio.run(
        respond_to_query("Hi tell me what clubs are at UCSC")
    )
    # Every organization is offered — the complete answer, not a sample.
    assert len(shown_ids) == len(clubs_data())

    payload = payload_of(message)
    assert payload is not None, "the full roster must be a tappable card"

    # One compact chip per club, each tapping straight through to its detail.
    selections = selections_of(payload)
    tappable_ids = {
        sel["club_id"] for sel in selections if "club_id" in sel and "action" not in sel
    }
    assert tappable_ids == {club["id"] for club in clubs_data()}

    # Chips stay small: label plus action only. A description, badges, or a
    # separate per-row action button would make the roster unusably tall.
    club_chips = [
        button
        for button in _card_buttons(payload)
        if "club_id" in button["action"]["selection"]
    ]
    assert len(club_chips) == len(clubs_data())
    for chip in club_chips:
        assert set(chip) == {"type", "label", "primary", "action"}

    # The label is the club's own name, so the grid is scannable.
    chip_labels = {chip["label"].removeprefix("✅ ") for chip in club_chips}
    assert chip_labels == {club["name"] for club in clubs_data()}

    # Confirmed organizations are marked inline, since chips carry no badges.
    ticked = {
        chip["label"].removeprefix("✅ ")
        for chip in club_chips
        if chip["label"].startswith("✅ ")
    }
    assert ticked == {club["name"] for club in clubs_data() if club["verified"]}

    body = text_of(message)
    assert "getinvolved.ucsc.edu" in body  # honesty pointer still present

    # Narrowing down is one tap away too — every vibe rides along as a footer
    # button on the same card.
    vibes = {sel.get("vibe") for sel in selections if "vibe" in sel}
    from agents.clubs.cards import VIBES

    assert vibes == {key for key, _, _, _ in VIBES}


@pytest.mark.parametrize(
    "text",
    [
        "what clubs are at UCSC",
        "tell me the clubs",
        "which orgs do you have?",
        "what organizations are there",
        "hi, please show me clubs",
    ],
)
def test_generic_club_asks_all_get_results(text):
    from agents.clubs.search import build_query, select

    scored, _ = select(build_query(text))
    assert scored, f"{text!r} returned nothing"


def test_specific_queries_are_not_swallowed_by_browse():
    """"clubs about hiking" must stay a hiking match, not become a spread."""
    from agents.clubs.search import build_query

    query = build_query("clubs about hiking")
    assert query.tags  # interest detected
    query = build_query("show me cultural orgs")
    assert query.category == "cultural_identity"


def test_nonsense_still_matches_nothing():
    """Hardening the generic path must not break honest no-matches."""
    from agents.clubs.search import build_query, select

    scored, total = select(build_query("quantum basket weaving underwater"))
    assert scored == []
    assert total == 0
