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
import sys
from datetime import date

from agents.clubs.service import respond_to_query as clubs_query
from agents.clubs.service import respond_to_selection as clubs_selection
from agents.events.service import respond_to_query as events_query
from agents.events.service import respond_to_selection as events_selection
from common.loader import clubs, events, transit_meta
from uagents_core.contrib.protocols.chat import TextContent

DURING = date(2026, 9, 22)

failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)


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
    message, _ = await events_query("show me the whole week", today=DURING)
    body = text_of(message)
    check(
        "unofficial" in body.lower(),
        "events listing: placeholder entries are not labelled 'unofficial'.",
    )
    check(
        "welcome.ucsc.edu" in body,
        "events listing: no pointer to the official schedule.",
    )
    check(
        "time not yet published" in body,
        "events listing: unpublished times are not stated as unpublished.",
    )

    for event in events():
        detail = text_of(events_selection(event["id"]))
        if event["verified"]:
            check(
                "Placeholder example" not in detail.split("**Also on")[0],
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
    message, _ = await clubs_query("show me cultural orgs")
    body = text_of(message)
    check(
        "unofficial" in body.lower(),
        "clubs listing: entries are not labelled 'unofficial'.",
    )
    check(
        "representative examples" in body,
        "clubs listing: missing the 'representative examples' caveat.",
    )
    check(
        "getinvolved.ucsc.edu" in body,
        "clubs listing: no pointer to the official directory.",
    )

    for club in clubs():
        detail = text_of(clubs_selection(club["id"]))
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
        # The only email address anywhere should be the official SOAR one.
        residue = detail.replace("soar@ucsc.edu", "")
        check(
            "@" not in residue,
            f"club detail {club['id']}: contains an email address other than the "
            "official SOAR contact.",
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
    await check_rendered_events()
    await check_rendered_clubs()
    await check_rendered_navigation()

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
