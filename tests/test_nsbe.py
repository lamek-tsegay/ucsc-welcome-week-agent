"""The NSBE chapter agent: routing, provenance, and what it refuses to invent.

This agent breaks a rule the clubs agent enforces — it states a contact address
and a meeting time — so the tests that matter most are the ones pinning *why*
that is allowed here: every such fact is published by the chapter itself, cited,
and dated. Everything the chapter has not published stays absent.
"""

from __future__ import annotations

import json
import re

import pytest

from agents.nsbe import cards
from agents.nsbe.service import detect_topic, respond_to_query, respond_to_topic
from agents_shared.loader import nsbe
from uagents_core.contrib.protocols.chat import MetadataContent, TextContent


def _text(message) -> str:
    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def _card(message) -> str:
    for item in message.content:
        if isinstance(item, MetadataContent):
            return item.metadata["card_payload"]
    return ""


def _rendered(message) -> str:
    return _text(message) + _card(message)


# --- data provenance ----------------------------------------------------------


def test_every_source_records_a_url_and_a_read_date():
    for name, source in nsbe()["_meta"]["sources"].items():
        assert source["url"].startswith("https://"), name
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["checked"]), name


def test_every_fact_cites_a_source_that_exists():
    """A citation pointing at nothing is worse than no citation."""
    data = nsbe()
    known = set(data["_meta"]["sources"])

    cited = [
        data["chapter"]["mission_source"],
        data["chapter"]["about_source"],
        data["chapter"]["parent_organization"]["source"],
        data["chapter"]["affiliation"]["source"],
        data["meetings"]["source"],
        data["contact"]["source"],
        *[link["source"] for link in data["links"]],
        *[step["source"] for step in data["join_steps"]],
    ]
    for source in cited:
        assert source in known, source


def test_links_are_all_https():
    for link in nsbe()["links"]:
        assert link["url"].startswith("https://"), link["id"]


def test_links_are_grouped_sensibly():
    """Social media adjacent, websites adjacent, the linktree last.

    The links card renders in data order, so the grouping lives in the data.
    The linktree closes the list because it contains everything above it —
    a catch-all in the middle read as just another link.
    """
    order = [link["id"] for link in nsbe()["links"]]
    assert order == ["instagram", "linkedin", "site", "national", "resume", "linktree"]


def test_no_officer_names_or_event_dates_anywhere():
    """The chapter publishes neither. Inventing them is the failure this whole
    project is built to prevent, and a club agent is where the temptation is
    strongest."""
    blob = json.dumps(nsbe()).lower()
    for banned in ("president", "vice president", "treasurer", "secretary", "e-board"):
        # The word may appear in the not_recorded note explaining its absence.
        occurrences = blob.count(banned)
        allowed = nsbe()["_meta"]["not_recorded"].lower().count(banned)
        assert occurrences == allowed, f"{banned!r} appears as data, not just as a caveat"


# --- routing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("when do they meet", "meetings"),
        ("what time is the meeting", "meetings"),
        ("where do you meet", "meetings"),
        ("how do I join", "join"),
        ("how do I get involved", "join"),
        ("can I sign up", "join"),
        ("what is NSBE", "about"),
        ("what's your mission", "about"),
        ("what's their instagram", "links"),
        ("do you have a linkedin", "links"),
    ],
)
def test_published_questions_route_to_their_topic(question, expected):
    assert detect_topic(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "who is the president",
        "who runs the chapter",
        "who's on the board",
        "when is your next event",
        "how much are dues",
        "what does membership cost",
    ],
)
def test_unpublished_questions_are_not_answered(question):
    """These have no published answer, so they must not be routed into a card
    that would imply one."""
    assert detect_topic(question) is None

    rendered = _rendered(respond_to_query(question))
    assert "don't hold" in rendered or "only know what" in rendered
    # And it hands off rather than dead-ending.
    assert "nsbe@ucsc.edu" in rendered


# --- what the cards say -------------------------------------------------------


def test_meeting_details_never_appear_without_their_read_date():
    """A meeting time is the fact most likely to go stale without the page
    changing, so it is never stated bare."""
    rendered = _rendered(cards.meetings_message())
    meetings = nsbe()["meetings"]

    assert meetings["day"] in rendered
    assert meetings["time"] in rendered
    assert meetings["location"] in rendered
    assert meetings["checked"] in rendered, "no read date alongside the meeting time"

    # The reply still points at where changes are announced — by name, with
    # the URL one tap away behind 🔗 Their links. A dedicated Instagram button
    # beside that one was the same destination twice, removed by request.
    assert "Instagram" in rendered, "no pointer to where changes appear"
    payload = json.loads(_card(cards.meetings_message()))
    topics = set()

    def walk(node):
        if isinstance(node, dict):
            selection = node.get("action", {}).get("selection", {}) if node.get("type") == "button" else {}
            if selection.get("topic"):
                topics.add(selection["topic"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    assert "links" in topics, "no route to the links card from meetings"


def test_mission_is_quoted_verbatim():
    mission = nsbe()["chapter"]["mission"]
    assert nsbe()["chapter"]["mission_is_quote"] is True
    assert mission in _rendered(cards.about_message())


def _redirects(payload) -> set[str]:
    """Every address a button opens directly, via `action.redirect`."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button" and "redirect" in node["action"]:
                found.add(node["action"]["redirect"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def _link_taps(payload) -> set[str]:
    """Every link a button asks the agent for instead of opening itself."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button":
                selection = node["action"].get("selection", {})
                if selection.get("action") == "open_link":
                    found.add(selection.get("link", ""))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def _url(link_id: str) -> str:
    return next(link["url"] for link in nsbe()["links"] if link["id"] == link_id)


def test_join_card_offers_every_published_route():
    """The routes are buttons, not URLs in the text — a URL there gets unfurled
    into a preview card. The linktree opens in one tap and carries Instagram
    and everything else, which is why there is no separate Instagram button;
    email opens Gmail pre-addressed to the chapter's own published address."""
    payload = json.loads(_card(cards.join_message()))
    redirects = _redirects(payload)

    assert _url("linktree") in redirects
    assert _url("instagram") not in redirects, "the redundant Instagram button is back"
    compose = [url for url in redirects if "mail.google.com" in url]
    assert compose, "no button opens a pre-addressed email"
    assert f"to={nsbe()['contact']['email']}" in compose[0], compose[0]

    # The meeting details still appear, composed from one source.
    assert nsbe()["meetings"]["location"] in _rendered(cards.join_message())


def test_links_card_opens_every_link_in_one_tap():
    """Six URLs in the bubble would be six preview cards. Each is a button
    that opens the page itself."""
    payload = json.loads(_card(cards.links_message()))

    assert _redirects(payload) == {link["url"] for link in nsbe()["links"]}
    assert "http" not in _text(cards.links_message())


def test_every_link_has_a_text_fallback():
    """A client that ignores the url sends the tap instead; every link must
    have something to say back."""
    for link in nsbe()["links"]:
        rendered = _text(cards.link_fallback_message(link["id"]))
        assert link["url"] in rendered, link["id"]


def test_contact_address_is_the_chapters_own():
    """The only email anywhere is the one the chapter publishes."""
    for builder in (
        cards.welcome_message,
        cards.meetings_message,
        cards.join_message,
        cards.about_message,
        cards.links_message,
        cards.unknown_message,
    ):
        rendered = _rendered(builder())
        residue = rendered.replace("nsbe@ucsc.edu", "")
        assert "@" not in residue.replace("@nsbe.ucsc", ""), builder.__name__


def test_about_data_card_shows_where_everything_came_from():
    rendered = _text(cards.about_data_message())
    for source in nsbe()["_meta"]["sources"].values():
        assert source["url"] in rendered
        assert source["checked"] in rendered
    assert "not" in rendered.lower()


# --- every topic is reachable and renders ------------------------------------


@pytest.mark.parametrize("topic", ["meetings", "join", "about", "links", "home"])
def test_every_topic_renders_a_card(topic):
    message = respond_to_topic(topic)
    payload = _card(message)
    assert payload, f"{topic} produced no card"
    root = json.loads(payload)["root"]
    assert root.get("title")
    assert root.get("children")


def test_every_card_button_leads_somewhere_real():
    """A button whose topic the service does not handle would dead-end."""
    known = {"meetings", "join", "about", "links", "home"}
    for builder in (
        cards.welcome_message,
        cards.meetings_message,
        cards.join_message,
        cards.about_message,
        cards.links_message,
        cards.unknown_message,
    ):
        payload = json.loads(_card(builder()))
        found: list[dict] = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "button" and "selection" in node["action"]:
                    found.append(node["action"]["selection"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for entry in node:
                    walk(entry)

        walk(payload)
        assert found or _redirects(payload), builder.__name__
        for selection in found:
            # A button either navigates to a known topic or asks the agent for
            # a link it does not open itself.
            if selection.get("action") == "open_link":
                assert selection.get("link"), (
                    f"{builder.__name__}: link button names no link"
                )
                continue
            assert selection.get("topic") in known, (
                f"{builder.__name__}: button goes to {selection.get('topic')!r}"
            )
