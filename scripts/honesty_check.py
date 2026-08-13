"""Data honesty gate.

Two of these agents talk about real events at a real university on real dates,
built on curated seed data. A student who acts on a placeholder as though it were
the official schedule is worse off than one who got no answer at all.

This script enforces that at the data and rendering layers together, and exits
non-zero on any violation. Run it after any data edit:

    make check

It checks things the unit tests cannot: that the *rendered output* a student
actually reads carries the right labelling, not just that the flags are set.
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import date

from agents.clubs.service import respond_to_query as clubs_query
from agents.clubs.service import respond_to_selection as clubs_selection
from agents.events.service import respond_to_query as events_query
from agents.events.service import respond_to_selection as events_selection
from agents_shared.loader import clubs, events, nsbe, transit_meta
import json

from uagents_core.contrib.protocols.chat import MetadataContent, TextContent

DURING = date(2026, 9, 22)

failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def card_text(message) -> str:
    """All text rendered on a message's card, footnotes included."""
    for item in message.content:
        if isinstance(item, MetadataContent):
            return json.dumps(json.loads(item.metadata["card_payload"]))
    return ""


def card_items(message) -> list[dict]:
    """Every list-card item in a message, as {heading, body, badges}.

    Listings render their records on the card rather than in the text bubble,
    so the labelling rules have to be checked where the student actually reads
    them. Verifying only the text would let an unlabelled card pass.
    """
    payload = None
    for item in message.content:
        if isinstance(item, MetadataContent):
            payload = json.loads(item.metadata["card_payload"])
            break
    if payload is None:
        return []

    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("type") == "list":
                for entry in node.get("items", []):
                    record = {"heading": "", "body": "", "badges": []}

                    def collect(inner) -> None:
                        if isinstance(inner, dict):
                            kind = inner.get("type")
                            if kind == "heading":
                                record["heading"] = inner.get("value", "")
                            elif kind == "text":
                                record["body"] += inner.get("value", "")
                            elif kind == "badge":
                                record["badges"].append(inner.get("label", ""))
                            for value in inner.values():
                                collect(value)
                        elif isinstance(inner, list):
                            for value in inner:
                                collect(value)

                    collect(entry)
                    found.append(record)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(payload)
    return found


def text_of(message) -> str:
    return "\n".join(
        item.text for item in message.content if isinstance(item, TextContent)
    )


def check_event_data() -> None:
    for event in events():
        if event["verified"]:
            check(
                event["time"] is None,
                f"events.json: {event['id']} is verified but has a time "
                f"({event['time']!r}). The official source publishes no times, so "
                "any value here is fabricated.",
            )
            check(
                bool(event.get("source")),
                f"events.json: {event['id']} is verified but cites no source.",
            )
        else:
            check(
                event.get("source") is None,
                f"events.json: {event['id']} is unverified but cites a source, "
                "which implies confirmation it does not have.",
            )


# Official UCSC pages a club's existence may be verified against. A verified
# club without a source on this list is a contract violation.
_OFFICIAL_CLUB_SOURCES = (
    "https://undergrad.engineering.ucsc.edu/",
)


def check_club_data() -> None:
    for club in clubs():
        if club["verified"]:
            source = club.get("source", "")
            check(
                any(source.startswith(root) for root in _OFFICIAL_CLUB_SOURCES),
                f"clubs.json: {club['id']} is verified=True but its source "
                f"({source!r}) is not an official UCSC page. Verification "
                "means confirmed against a citable official source — nothing "
                "else counts.",
            )
            check(
                bool(club.get("source_checked")),
                f"clubs.json: {club['id']} is verified but records no "
                "source_checked date.",
            )
        else:
            check(
                not club.get("website"),
                f"clubs.json: {club['id']} is unverified but carries a website. "
                "Links may only come from a confirmed official source page.",
            )
        check(
            club["contact"] is None,
            f"clubs.json: {club['id']} carries a contact value. A wrong address "
            "sends students to the wrong place — omit rather than guess. This "
            "holds for verified clubs too: their own site is the authority.",
        )
        check(
            club["meeting_info"] is None,
            f"clubs.json: {club['id']} carries meeting_info. Meeting times are "
            "not knowable from here and must not be invented.",
        )


def check_transit_data() -> None:
    meta = transit_meta()
    check(
        meta.get("verified") is False,
        "transit.json: must be marked verified=false — route data is approximate.",
    )
    for key in ("frequency", "frequencies", "operating_hours", "schedule"):
        check(
            key not in meta,
            f"transit.json: found {key!r}. Frequencies and hours are deliberately "
            "omitted rather than guessed.",
        )


async def check_rendered_events() -> None:
    message, shown_ids = await events_query("show me the whole week", today=DURING)
    rendered = text_of(message) + card_text(message)
    check(
        "welcome.ucsc.edu" in rendered,
        "events listing: no pointer to the official schedule.",
    )

    # Events render on the card, so each one carries its own verification badge
    # and its own time — including the refusal to invent one.
    by_id = {event["id"]: event for event in events()}
    items = card_items(message)
    check(
        len(items) == len(shown_ids),
        f"events listing: card shows {len(items)} events but the reply claims "
        f"{len(shown_ids)}.",
    )
    for event_id, item in zip(shown_ids, items):
        event = by_id[event_id]
        expected = "Confirmed" if event["verified"] else "Unofficial"
        check(
            expected in item["badges"],
            f"events listing: {event_id} is missing its {expected!r} badge on "
            f"the card (badges: {item['badges']}).",
        )
        if event["time"] is None:
            check(
                "time not yet published" in item["body"],
                f"events listing: {event_id} has no published time but the "
                "card does not say so.",
            )

    for event in events():
        # Detail content lives on the card, so check the whole rendered payload.
        message = events_selection(event["id"])
        detail = text_of(message) + card_text(message)
        if event["verified"]:
            check(
                # The card is about this event alone — no sibling block — so
                # the whole reply must be free of placeholder language.
                "Placeholder example" not in detail,
                f"event detail {event['id']}: confirmed event is labelled a "
                "placeholder.",
            )
        else:
            check(
                "Placeholder example" in detail,
                f"event detail {event['id']}: placeholder is NOT labelled as one.",
            )
        if event["time"] is None:
            check(
                "time not yet published" in detail,
                f"event detail {event['id']}: missing time is not stated.",
            )


async def check_rendered_clubs() -> None:
    message, shown_ids = await clubs_query("show me cultural orgs")
    # The caveat rides on the card as a muted footnote rather than above the
    # results, so it is checked in the payload the student actually sees.
    rendered = text_of(message) + card_text(message)
    check(
        "not a live roster" in rendered,
        "clubs listing: missing the not-a-live-roster caveat.",
    )
    check(
        "getinvolved.ucsc.edu" in rendered,
        "clubs listing: no pointer to the official directory.",
    )

    # Organizations render on the card, so every one must carry its own
    # verification badge there.
    by_id = {club["id"]: club for club in clubs()}
    items = card_items(message)
    check(
        len(items) == len(shown_ids),
        f"clubs listing: card shows {len(items)} organizations but the reply "
        f"claims {len(shown_ids)}.",
    )
    for club_id, item in zip(shown_ids, items):
        club = by_id[club_id]
        expected = "Confirmed" if club["verified"] else "Unofficial"
        check(
            expected in item["badges"],
            f"clubs listing: {club_id} is missing its {expected!r} badge on "
            f"the card (badges: {item['badges']}).",
        )

    for club in clubs():
        # Detail content lives on the card, so the whole rendered payload is
        # what a student reads — check there, not just the text bubble.
        message = clubs_selection(club["id"])
        detail = text_of(message) + card_text(message)
        if club["verified"]:
            # Confirmed orgs cite their official source instead of the roster
            # caveat — but must never overstate what "confirmed" means.
            check(
                "Baskin Engineering" in detail,
                f"club detail {club['id']}: verified but does not cite the "
                "Baskin Engineering source page.",
            )
            if club.get("website"):
                check(
                    club["website"] in detail,
                    f"club detail {club['id']}: has an official site but does "
                    "not show it.",
                )
        else:
            check(
                "not a live roster entry" in detail,
                f"club detail {club['id']}: missing the not-a-live-roster caveat.",
            )
        check(
            "soar@ucsc.edu" in detail,
            f"club detail {club['id']}: no official contact route offered.",
        )
        # SOAR's address is always allowed. A club's own address is allowed too,
        # but only the one its profile records — which exists only because that
        # club's own site was read and cited, the same standard the NSBE agent
        # meets. Any other address on the card is a guess.
        allowed = {"soar@ucsc.edu"}
        profile = club.get("profile")
        if profile and profile.get("contact_email"):
            check(
                bool(profile.get("source")) and bool(profile.get("checked")),
                f"clubs.json: {club['id']} profile states a contact address "
                "without recording where it came from and when it was read.",
            )
            allowed.add(profile["contact_email"])

        residue = detail
        for address in allowed:
            residue = residue.replace(address, "")
        check(
            "@" not in residue,
            f"club detail {club['id']}: contains an email address that is "
            "neither SOAR's nor one read from the club's own site.",
        )

        # Everything a profile asserts is only as good as its citation.
        if profile:
            check(
                profile.get("source", "").startswith("https://")
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", profile.get("checked", "")),
                f"clubs.json: {club['id']} profile needs an https source and an "
                "ISO read date.",
            )
            check(
                profile["source"] in detail or profile["checked"] in detail,
                f"club detail {club['id']}: renders profile content without "
                "saying when it was read.",
            )
            for field in ("summary", "mission", "who_can_join"):
                if profile.get(field):
                    check(
                        isinstance(profile.get(f"{field}_is_quote"), bool),
                        f"clubs.json: {club['id']} profile {field!r} does not "
                        "record whether it is the club's wording or ours.",
                    )


def check_nsbe_data() -> None:
    """The club agent states a meeting time and a contact address, which the
    clubs dataset never does. That is only defensible while every such fact is
    published by the chapter, cited, and dated — so the gate checks exactly
    that, and that nothing unpublished has crept in."""
    data = nsbe()
    known = set(data["_meta"]["sources"])

    for name, source in data["_meta"]["sources"].items():
        check(
            source["url"].startswith("https://") and bool(source.get("checked")),
            f"nsbe.json: source {name} lacks an https url or a read date.",
        )

    check(
        data["meetings"].get("source") in known
        and bool(data["meetings"].get("checked")),
        "nsbe.json: the meeting time is stated without a cited, dated source.",
    )
    check(
        data["contact"].get("source") in known,
        "nsbe.json: the contact address is stated without a cited source.",
    )
    for link in data["links"]:
        check(
            link.get("source") in known and link["url"].startswith("https://"),
            f"nsbe.json: link {link['id']} lacks an https url or a cited source.",
        )

    # Nothing the chapter has not published.
    blob = json.dumps(
        {k: v for k, v in data.items() if k != "_meta"}
    ).lower()
    for banned in ("president", "treasurer", "secretary", "e-board", "vice chair"):
        check(
            banned not in blob,
            f"nsbe.json: contains {banned!r}, which the chapter does not publish.",
        )


async def check_rendered_nsbe() -> None:
    from agents.nsbe import cards as nsbe_cards

    meetings = nsbe()["meetings"]
    rendered = text_of(nsbe_cards.meetings_message()) + card_text(
        nsbe_cards.meetings_message()
    )
    check(
        meetings["checked"] in rendered,
        "nsbe meetings card: states a meeting time with no read date.",
    )
    check(
        # Named, not linked: the URL lives one tap away behind 🔗 Their links.
        # A dedicated Instagram button beside that one was the same
        # destination twice, removed by request 2026-08-12.
        "Instagram" in rendered,
        "nsbe meetings card: no pointer to where changes are announced.",
    )

    # The only address anywhere is the chapter's own.
    for builder in (
        nsbe_cards.welcome_message,
        nsbe_cards.meetings_message,
        nsbe_cards.join_message,
        nsbe_cards.about_message,
        nsbe_cards.links_message,
        nsbe_cards.unknown_message,
    ):
        body = text_of(builder()) + card_text(builder())
        residue = body.replace("nsbe@ucsc.edu", "").replace("@nsbe.ucsc", "")
        check(
            "@" not in residue,
            f"nsbe {builder.__name__}: shows an address other than the chapter's.",
        )


async def check_rendered_navigation() -> None:
    from agents.navigation.service import answer

    reply = await answer("from Cowell to Science Hill")
    check(
        "estimate" in reply.lower(),
        "navigation: walking times are not presented as estimates.",
    )

    located = await answer("where is Quarry Plaza")
    check(
        "approximate" in located.lower(),
        "navigation: coordinates are not described as approximate.",
    )

    accessible = await answer("step-free route from Cowell to the bookstore")
    check(
        "Disability Resource Center" in accessible,
        "navigation: accessible routing does not flag incomplete data.",
    )

    with_bus = await answer(
        "wheelchair accessible route from quarry plaza to science hill"
    )
    if "Bus alternative" in with_bus:
        check(
            "unverified" in with_bus.lower(),
            "navigation: bus suggestion is not marked unverified.",
        )

    # The relaxed-constraint note must not point at a bus that isn't shown.
    relaxed = await answer("route from Oakes to Science Hill avoiding hills")
    if "consider the bus below" in relaxed:
        check(
            "Bus alternative" in relaxed,
            "navigation: promises a bus alternative that is not in the reply.",
        )


async def main() -> int:
    check_event_data()
    check_club_data()
    check_transit_data()
    check_nsbe_data()
    await check_rendered_events()
    await check_rendered_clubs()
    await check_rendered_navigation()
    await check_rendered_nsbe()

    print(f"Honesty check: {checks} assertions across data and rendered output.")
    if failures:
        print(f"\nFAILED ({len(failures)}):\n")
        for failure in failures:
            print(f"  ✗ {failure}")
        return 1

    print("All clear — no unverified content is presented as official, and no")
    print("unpublished time, contact, or schedule is invented.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
