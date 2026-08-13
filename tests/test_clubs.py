"""Club search, interest matching, and response shape."""

from __future__ import annotations

import asyncio
import json

import pytest

from agents.clubs.search import (
    ClubQuery,
    build_query,
    by_id,
    category_label,
    detect_category,
    detect_tags,
    select,
    similar,
)
from agents.clubs.service import respond_to_query, respond_to_selection
from agents_shared.loader import clubs
from uagents_core.contrib.protocols.chat import MetadataContent, TextContent


def _text(message) -> str:
    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def _has_card(message) -> bool:
    return any(isinstance(item, MetadataContent) for item in message.content)


def _card_text(message) -> str:
    """Everything rendered on the card, footnote included.

    Source pointers and caveats ride on the card as a muted footnote rather
    than above the results, so assertions about them look here."""
    for item in message.content:
        if isinstance(item, MetadataContent):
            return item.metadata["card_payload"]
    return ""


# --- interest and category detection -----------------------------------------


@pytest.mark.parametrize(
    "text,expected_tag",
    [
        ("clubs about hiking", "hiking"),
        ("I'm into anime", "anime"),
        ("I like surfing", "surfing"),
        ("anything for pre-med students", "premed"),
        ("I want to code", "programming"),
        ("robotics", "robotics"),
        ("I like singing", "singing"),
        ("volunteering opportunities", "volunteering"),
        ("climate stuff", "environment"),
        ("board games", "board-games"),
    ],
)
def test_detect_tags(text, expected_tag):
    assert expected_tag in detect_tags(text), text


def test_detect_tags_avoids_substring_false_positives():
    """'art' must not fire on 'start' or 'party'."""
    assert "art" not in detect_tags("when does it start")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("show me cultural orgs", "cultural_identity"),
        ("tech clubs", "tech_engineering"),
        ("sports clubs", "sports_recreation"),
        ("greek life", "greek"),
        ("media organizations", "media_publication"),
        ("service orgs", "service_advocacy"),
    ],
)
def test_detect_category(text, expected):
    assert detect_category(text) == expected


def test_category_labels_resolve():
    assert category_label("cultural_identity") == "Cultural & Identity"
    assert category_label("unknown_thing") == "Unknown Thing"


# --- selection ----------------------------------------------------------------


def test_interest_search_finds_the_obvious_club():
    scored, _ = select(build_query("clubs about hiking"), limit=10)
    ids = [item.club["id"] for item in scored]
    assert "c_hiking" in ids
    assert ids[0] == "c_hiking", "the most on-the-nose match should lead"


def test_name_lookup_ranks_first():
    scored, _ = select(build_query("surf club"), limit=10)
    assert scored[0].club["id"] == "c_surf"


def test_category_browse_returns_that_category():
    query = ClubQuery(category="tech_engineering")
    scored, _ = select(query, limit=20)
    assert scored
    assert all(item.club["category"] == "tech_engineering" for item in scored)


def test_select_reports_total_for_truncation():
    query = ClubQuery(category="cultural_identity")
    scored, total = select(query, limit=3)
    assert len(scored) == 3
    assert total > 3


def test_empty_query_offers_a_spread_across_categories():
    scored, _ = select(build_query("show me everything"), limit=10)
    categories = [item.club["category"] for item in scored]
    assert len(set(categories)) == len(categories), "should not repeat a category"
    assert len(categories) >= 5


def test_nonsense_query_matches_nothing():
    scored, total = select(build_query("quantum basket weaving underwater"))
    assert scored == []
    assert total == 0


def test_similar_returns_same_category_excluding_self():
    club = by_id("c_anime")
    assert club is not None
    others = similar(club)
    assert others
    assert all(other["category"] == club["category"] for other in others)
    assert all(other["id"] != club["id"] for other in others)


# --- data contract ------------------------------------------------------------


def test_verified_clubs_cite_an_official_source():
    """Two-tier contract: verified=true requires a citable official UCSC page.

    The RSO directory is JS-rendered and unconfirmable, so general entries stay
    verified=false. The Baskin Engineering student-organizations page is static
    and official, so orgs listed there are confirmable — but only with the
    source and check date recorded, and websites only ever come from that page.
    """
    for club in clubs():
        if club["verified"]:
            assert club.get("source", "").startswith(
                "https://undergrad.engineering.ucsc.edu/"
            ), club["id"]
            assert club.get("source_checked"), club["id"]
        else:
            assert not club.get("website"), (
                f"{club['id']}: unverified entries must not carry links"
            )


def test_both_tiers_are_present():
    """The dataset keeps confirmed orgs AND labelled examples — losing either
    silently would change what the agent honestly is."""
    flags = {club["verified"] for club in clubs()}
    assert flags == {True, False}


def test_no_club_carries_invented_contact_details():
    """A wrong address sends a student to the wrong place — omit, never guess."""
    for club in clubs():
        assert club["contact"] is None, club["id"]
        assert club["meeting_info"] is None, club["id"]


# --- responses ----------------------------------------------------------------


def test_response_includes_card_and_disclaimer():
    message, ids = asyncio.run(respond_to_query("clubs about hiking"))
    assert ids
    assert _has_card(message)
    rendered = _text(message) + _card_text(message)
    assert "getinvolved.ucsc.edu" in rendered
    assert "not a live roster" in rendered


def test_response_labels_every_entry_on_the_card():
    """Listings render organizations on the card, so that is where the
    verification badge has to be — the text bubble carries only the heading
    and the caveats."""
    message, shown_ids = asyncio.run(respond_to_query("show me cultural orgs"))
    assert shown_ids

    payload = json.loads(
        next(
            item for item in message.content if isinstance(item, MetadataContent)
        ).metadata["card_payload"]
    )
    badges: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "badge":
                badges.append(node.get("label", ""))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    lookup = {club["id"]: club for club in clubs()}
    for club_id in shown_ids:
        expected = "Confirmed" if lookup[club_id]["verified"] else "Unofficial"
        assert expected in badges, f"{club_id} missing its {expected} badge"


def test_browse_all_returns_every_club_in_one_card():
    """"Browse all UCSC clubs" lands on the whole list, not a picker.

    A category picker in front of it was one tap between the student and the
    thing they asked for, and the category is already legible from the emoji
    on each name.
    """
    from agents_shared.loader import clubs as clubs_data

    message, shown_ids = asyncio.run(respond_to_query("what categories are there"))
    assert len(shown_ids) == len(clubs_data())

    payload = json.loads(_card_text(message))
    # Names are list headings, not button labels: a button centres its own
    # label and the schema exposes no way to align it, so the names live in
    # headings, which the client left-aligns.
    labels: list[str] = []
    tappable: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "heading" and node.get("level") == 3:
                labels.append(node["value"])
            if node.get("type") == "button" and "club_id" in node["action"]["selection"]:
                tappable.append(node["action"]["selection"]["club_id"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    assert len(labels) == len(clubs_data())
    assert sorted(tappable) == sorted(club["id"] for club in clubs_data())

    # Alphabetical by club name — the emoji and tick prefixes must not drive
    # the ordering, or the list reads by codepoint instead of by name.
    # The confirmed tick trails the name rather than leading it, so every
    # name starts at the same point instead of confirmed ones being pushed in.
    lookup = {club["name"]: club for club in clubs_data()}
    names = []
    for label in labels:
        stripped = label.removesuffix(" ✅")
        name = next(n for n in lookup if stripped.endswith(n))
        names.append(name)
    assert names == sorted(names, key=str.lower)
    assert set(names) == set(lookup)

def test_no_match_response_suggests_alternatives():
    message, ids = asyncio.run(respond_to_query("quantum basket weaving underwater"))
    assert ids == []
    body = _text(message)
    assert "Cornucopia" in body


def test_selection_detail_points_at_official_sources():
    """Detail content lives on the card, so that is where the routes to the
    real thing have to be."""
    message = respond_to_selection("c_anime")
    rendered = _text(message) + _card_text(message)
    assert "Anime & Manga Club" in rendered
    assert "soar@ucsc.edu" in rendered
    assert "Cornucopia" in rendered
    assert "not a live roster entry" in rendered


def test_selection_detail_does_not_fabricate_contact():
    message = respond_to_selection("c_hiking")
    rendered = _text(message) + _card_text(message)
    assert "@" not in rendered.replace("soar@ucsc.edu", ""), (
        "the only email address shown should be the official SOAR contact"
    )


def test_unknown_selection_is_handled():
    assert "lost track" in _text(respond_to_selection("c_not_real"))


# --- approximate-match labelling ------------------------------------------
# Results reached only through the ASI:One fallback are guesses at what the
# student meant. Presenting them under a category heading reads as a real match,
# so they are labelled instead. These tests pin that boundary without a network
# call: conftest disables ASI:One, so the flag is set directly.

from agents.clubs.service import _heading as clubs_heading
from agents.clubs.search import ClubQuery, ScoredClub


def _scored(n):
    return [ScoredClub(club={"id": f"c{i}", "name": f"Club {i}"}, score=1.0) for i in range(n)]


def test_approximate_query_is_not_presented_as_a_category_match():
    query = ClubQuery(tags={"games", "hobby"}, category="special_interest", approximate=True)
    heading = clubs_heading(query, _scored(6), 6, "quantum basket weaving underwater")
    assert "Closest matches" in heading
    assert "quantum basket weaving underwater" in heading
    assert "nearest interests" in heading
    # The category must not be asserted as though the student asked for it.
    assert "Games, Hobbies" not in heading


def test_direct_keyword_match_keeps_its_authoritative_heading():
    query = ClubQuery(tags={"hiking", "outdoors"}, approximate=False)
    heading = clubs_heading(query, _scored(6), 6, "clubs about hiking")
    assert "Closest matches" not in heading
    assert "Matching hiking, outdoors" in heading


def test_named_lookup_outranks_approximate_flag():
    """A named club was found by name; that is a real match, not a guess."""
    query = ClubQuery(named="Anime & Manga Club", tags={"anime"}, approximate=True)
    heading = clubs_heading(query, _scored(1), 1, "anime club")
    assert "Found it" in heading
    assert "Closest matches" not in heading


def test_long_query_is_truncated_in_approximate_heading():
    from agents_shared.notices import approximate_match_heading

    heading = approximate_match_heading("x" * 200, 3, "organizations")
    assert "..." in heading
    assert len(heading.split("\n")[0]) < 120


# --- Baskin Engineering verified tier -----------------------------------------


def test_engineering_orgs_are_findable_by_acronym():
    """Students say "ACM" and "SHPE", not the full society names."""
    from agents.clubs.search import build_query, select

    for query_text, expected_id in [
        ("is there an ACM chapter", "be_acm"),
        ("SHPE", "be_shpe"),
        ("rocketry club", "be_rocket_team"),
        ("girls who code", "be_girls_who_code"),
        ("cybersecurity club", "be_slug_security"),
    ]:
        scored, _ = select(build_query(query_text))
        ids = [item.club["id"] for item in scored]
        assert expected_id in ids, f"{query_text!r} did not surface {expected_id}"


def test_verified_detail_cites_source_and_site():
    message = respond_to_selection("be_swe")
    rendered = _text(message) + _card_text(message)
    assert "Confirmed" in rendered
    assert "Baskin Engineering" in rendered
    assert "sweclub.engineering.ucsc.edu" in rendered  # the official page's link
    # And still no invented contact details:
    assert "@" not in rendered.replace("soar@ucsc.edu", "")


def test_verified_orgs_do_not_hijack_unrelated_categories():
    """A confirmed engineering org must not outrank cultural orgs on a
    cultural query just because it shares an identity tag."""
    from agents.clubs.service import respond_to_query

    message, shown_ids = asyncio.run(respond_to_query("show me cultural orgs"))
    top = shown_ids[:8]
    assert all(not cid.startswith("be_") for cid in top), top


def test_tech_queries_surface_verified_orgs_first():
    from agents.clubs.search import build_query, select

    scored, _ = select(build_query("robotics clubs"))
    assert scored, "robotics query matched nothing"
    assert scored[0].club["verified"], "top robotics result should be confirmed"
