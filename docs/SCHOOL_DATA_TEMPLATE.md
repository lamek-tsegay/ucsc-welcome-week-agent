# Data collection template — adding a new school

Everything you need to gather to stand these agents up for another university.
Hand this document to whoever is doing the collecting; it is written to be
usable without reading any code.

**Contents**

1. [Before you start](#1-before-you-start)
2. [School header](#2-school-header-fill-in-once)
3. [Events](#3-events)
4. [Clubs and organizations](#4-clubs-and-organizations)
5. [Campus places — only if you want the navigation agent](#5-campus-places--only-if-you-want-the-navigation-agent)
6. [How to send it](#6-how-to-send-it)
7. [Blank templates to copy](#7-blank-templates-to-copy)

---

## 1. Before you start

### The three rules

These are not style preferences. Each one is enforced by an automated check
that fails the build, because each one exists to stop the agent telling a
student something false.

**Rule 1 — Never write a time you are guessing.**
If the official page does not publish a time, leave `Time` blank. It renders
as *"time not yet published"*, which is honest and useful. A wrong time sends
someone to an empty field at the wrong hour. A confirmed event that carries a
time fails the check.

**Rule 2 — Never write club contact details or meeting times.**
Leave them blank always, even if you think you know them. A wrong email or a
stale meeting time sends a student to the wrong place, which is worse than
sending them to the official directory. The club's own website — only if an
official school page links it — is the authority.

**Rule 3 — "Confirmed" means you personally saw it on an official page.**
Nothing more. Not that the club is currently active, not that the time is
right, not that a friend told you. Confirmed requires a URL and the date you
looked. Everything else is marked unconfirmed, still works fully, and is
labelled *Unofficial* wherever it appears.

### Confirmed vs unconfirmed

Both are useful. Do not skip an entry because you cannot confirm it.

| | Confirmed | Unconfirmed |
|---|---|---|
| Means | Seen on an official school page on a stated date | A representative example |
| Needs | Source URL + check date | Nothing |
| Shown as | ✅ **Confirmed** badge | ⚠️ **Unofficial** badge |
| Sorting | Ranks above unconfirmed entries | Never outranks a confirmed one |
| Can carry a website | Yes, if the official page listed it | No |

A dataset that is entirely unconfirmed still produces a working, honest agent.
It just tells students plainly that its entries are examples.

---

## 2. School header (fill in once)

```
School name:               e.g. UC Santa Cruz
Short name:                e.g. UCSC
Welcome week name:         e.g. Slug Start / Welcome Week
Start date:                YYYY-MM-DD
End date:                  YYYY-MM-DD
Timezone:                  e.g. America/Los_Angeles
```

### Sub-communities

Some schools split first-year programming by residential unit — UCSC has ten
residential colleges, each with its own first-day schedule. If yours does, list
them; events can then be filtered to a student's own community.

```
Sub-community type:        college | dorm | house | none
Names:                     one per line, official spelling
Common nicknames:          e.g. "College 8" for Rachel Carson, "C9", "JRL"
```

Write `none` if the school does not work this way. Everything still works; the
"which one are you in?" step simply disappears.

### Official links

Used for the 🔗 Campus links card and for the "check the real source" pointers
that every reply carries. Only official school or transit-authority domains.
Leave a line blank if the school does not have one.

```
Welcome week schedule:
Club / student org directory:
Campus map:
Dining:
Campus transit:
City transit:
Library:
Student health:
Accessibility / disability services:
```

### Club support office

The office students should email when the agent does not know something.

```
Office name:               e.g. SOAR
Email:                     e.g. soar@ucsc.edu
```

### Involvement fair

The one in-person event where most organizations table. The clubs agent points
students at it constantly, because it is the honest answer to "how do I
actually join something".

```
Name:                      e.g. Cornucopia
Date:                      YYYY-MM-DD
Location:
```

---

## 3. Events

### Fields

| Field | Required | Notes |
|---|---|---|
| **Event name** | yes | As the school writes it |
| **Date** | yes | `YYYY-MM-DD`, must fall inside the welcome week window |
| **Time** | no | **Blank unless officially published.** See Rule 1 |
| **Location** | no | Venue name as written. Blank if not announced |
| **Description** | yes | 1–2 sentences on what actually happens |
| **Who it's for** | yes | `all` — or the sub-community names it is limited to |
| **Tags** | yes | 2–5 from the list below |
| **Confirmed?** | yes | `YES` / `NO` |
| **Source URL** | if confirmed | The official page you saw it on |
| **Date checked** | if confirmed | `YYYY-MM-DD` |

### Event tags

Pick 2–5. These drive the six interest buttons students tap, so an event with
no tags is reachable only by date.

| Tag | Use for |
|---|---|
| `food` | Anything with free food — meals, snacks, BBQs |
| `social` | Mixers, meetups, hangouts |
| `tradition` | Signature school traditions |
| `festival` | Large multi-org festivals |
| `orgs` | Club fairs, involvement events |
| `outdoors` | Hikes, beach trips, outdoor activity |
| `sports` | Athletics, intramurals, games |
| `recreation` | Gym, rec centre, casual activity |
| `arts` | Visual art, crafts, making things |
| `music` | Concerts, performances, open mics |
| `photo` | Photo ops, class photo |
| `academic` | Advising, study skills, library intros |
| `career` | Career fairs, professional prep |
| `jobs` | Student employment, work-study |
| `tech` | Hackathons, tech talks |
| `cultural` | Cultural centre and identity programming |
| `wellness` | Health, mindfulness, wellbeing |
| `tour` | Campus tours and walks |
| `offcampus` | Anything off campus |
| `exploration` | Discovering the town / area |
| `orientation` | Formal orientation sessions |
| `transfer` | Transfer-student specific |
| `evening` | Happens after dark |

**How tags become buttons.** Students never see raw tags — they see six
interests. Aim for coverage across all six so no button dead-ends:

| Interest button | Fed by tags |
|---|---|
| 🍕 Free food | `food` |
| 🎉 Meet people | `social` `orgs` `tradition` `festival` |
| 🌲 Outdoors & active | `outdoors` `sports` `recreation` |
| 🎨 Arts & music | `arts` `music` `photo` |
| 💼 Career & academic | `academic` `career` `jobs` `tech` |
| 🚌 Off campus | `offcampus` `tour` `exploration` |

### Worked example — confirmed

```
Event name:    Cornucopia
Date:          2026-09-22
Time:          (blank — official page publishes no times)
Location:      East Upper Field
Description:   The big campus festival where student organizations,
               departments, and campus services all set up tables.
Who it's for:  all
Tags:          festival, orgs, social, food
Confirmed?:    YES
Source URL:    https://welcome.ucsc.edu/slug-life/fall-welcome-week/
Date checked:  2026-08-09
```

### Worked example — unconfirmed

```
Event name:    Porter Arts Night
Date:          2026-09-23
Time:          (blank)
Location:      Porter College
Description:   Open studios, live music, and student art across the college.
Who it's for:  Porter, Kresge
Tags:          arts, music, social, evening
Confirmed?:    NO
Source URL:    (blank)
Date checked:  (blank)
```

---

## 4. Clubs and organizations

### Fields

| Field | Required | Notes |
|---|---|---|
| **Club name** | yes | Official name in full, not the acronym |
| **Acronym / nicknames** | no | `ACM`, `SWE`, `SHPE` — students search by these |
| **Category** | yes | Exactly one, from the ten below |
| **Description** | yes | One sentence on what they actually do |
| **Tags** | yes | 3–6 interest words |
| **Website** | no | **Only** if an official school page links it |
| **Confirmed?** | yes | `YES` / `NO` |
| **Source URL** | if confirmed | The official page you saw it on |
| **Date checked** | if confirmed | `YYYY-MM-DD` |
| **Contact** | — | **Always blank.** See Rule 2 |
| **Meeting times** | — | **Always blank.** See Rule 2 |

### Categories — exactly one per club

| id | Shown as |
|---|---|
| `cultural_identity` | Cultural & Identity |
| `academic_professional` | Academic & Professional |
| `arts_performance` | Arts & Performance |
| `media_publication` | Media & Publications |
| `sports_recreation` | Sports & Recreation |
| `service_advocacy` | Service & Advocacy |
| `tech_engineering` | Technology & Engineering |
| `spiritual` | Spiritual & Religious |
| `greek` | Fraternity & Sorority Life |
| `special_interest` | Games, Hobbies & Special Interest |

### Club tags

Free-form, but reuse these wherever they fit — they feed the interest buttons.
Anything outside this list still helps keyword search, it just will not surface
from a button tap.

`hiking` `climbing` `surfing` `cycling` `fitness` `sports` `outdoors`
`music` `singing` `dance` `theater` `comedy` `performance` `art` `arts`
`creative` `writing` `journalism` `media` `radio`
`games` `gaming` `anime` `manga` `tabletop` `board-games` `esports`
`tech` `programming` `robotics` `engineering` `ai` `security` `science`
`research` `academic` `debate` `premed` `law` `business` `finance` `career`
`leadership` `service` `volunteering` `advocacy` `support` `environment`
`sustainability` `cultural` `identity` `lgbtq` `international` `community`
`social` `spiritual` `wellness` `health` `food` `cooking` `greek`

| Interest button | Fed by tags |
|---|---|
| 🎨 Creative & artsy | `arts` `art` `creative` `music` `theater` `performance` `writing` `media` |
| 🏃 Active & outdoors | `sports` `fitness` `outdoors` `hiking` `climbing` `surfing` `cycling` |
| 🧠 Curious & academic | `academic` `research` `science` `debate` `career` `leadership` `tech` `engineering` `programming` |
| 🎮 Chill & playful | `games` `gaming` `social` `food` |
| 🌍 Cultural & global | `cultural` `identity` `international` `community` |
| 💪 Service & impact | `service` `advocacy` `support` |

### Worked example — confirmed

```
Club name:       Society of Women Engineers
Acronym:         SWE, SWESLUGS
Category:        tech_engineering
Description:     UCSC section of the Society of Women Engineers.
Tags:            engineering, identity, community, career
Website:         https://sweclub.engineering.ucsc.edu/
Confirmed?:      YES
Source URL:      https://undergrad.engineering.ucsc.edu/student-organizations/
Date checked:    2026-08-09
Contact:         (blank — always)
Meeting times:   (blank — always)
```

### Worked example — unconfirmed

```
Club name:       Hiking & Backpacking Club
Acronym:         (blank)
Category:        sports_recreation
Description:     Weekend hikes in the campus redwoods and nearby mountains.
Tags:            hiking, outdoors, nature, fitness, social
Website:         (blank — not on an official page)
Confirmed?:      NO
Source URL:      (blank)
Date checked:    (blank)
Contact:         (blank — always)
Meeting times:   (blank — always)
```

### Where to find confirmable clubs

Most schools publish a JavaScript-rendered club directory that cannot be
verified from a static read — those entries stay unconfirmed. But **departmental
pages are often plain HTML and official**, and are a rich source of confirmable
organizations. At UCSC the engineering school's page yielded 35 confirmed orgs
with working links. Check:

- Engineering / CS school student-organization pages
- Business school club listings
- Cultural centre or identity-centre org lists
- Greek life council pages
- Recreation / club sports listings

---

## 5. Campus places — only if you want the navigation agent

**Skip this section unless you need walking directions.** The events and clubs
agents work fully without it. This is by far the most laborious data to
collect, and it is only worth it for a campus where getting around is genuinely
hard — UCSC is 2,000 acres of forested hillside, so it was.

### Landmarks

One row per place. UCSC has 54.

| Field | Required | Notes |
|---|---|---|
| **Name** | yes | Official building or place name |
| **Aliases** | yes | What students actually call it — "the gym", "sci hill", "c9" |
| **Category** | yes | `college` `academic` `library` `dining` `recreation` `services` `venue` `transit` `landmark` `offcampus` |
| **Latitude / Longitude** | yes | 5 decimal places is plenty; approximate is fine and is labelled as such |
| **Elevation (ft)** | if hilly | Drives the effort meter and hill avoidance |
| **Sub-community** | no | Which college/dorm it belongs to, if any |
| **Notes** | no | One line — what it is, why you'd go |

### Walking connections

One row per direct path between two landmarks. UCSC has 58. Only connect
places that are genuinely adjacent — the router chains them for longer trips.

| Field | Required | Notes |
|---|---|---|
| **From / To** | yes | Landmark names |
| **Minutes** | yes | Unhurried walking pace, including the terrain |
| **Elevation change (ft)** | if hilly | Positive = uphill in the From→To direction |
| **Via** | no | "the stepped path behind Kresge" — shown in directions |
| **Flags** | no | `steep` `stairs` `unlit` `paved` `offcampus` `bus_strongly_recommended` |

`stairs` and `steep` power step-free routing; `unlit` powers after-dark
warnings. Getting these right matters more than precise minutes — a student who
needs a step-free route is relying on them.

### Transit (optional)

```
Route name:
Kind:               campus_shuttle | metro
Stops in order:     landmark names, in travel order
Minutes between consecutive stops:
Note:               e.g. "runs counter-clockwise around the loop"
```

Do **not** record frequencies or operating hours — they change, and a stale
schedule is worse than none. The agent points at the transit authority's live
site instead.

---

## 6. How to send it

**Best: a spreadsheet.** One tab for events, one for clubs, one column per
field name above, one row per record. Missing fields are obvious at a glance,
and it is easy for several people to fill in together.

**Fine: plain text** in the block format shown in the worked examples, one
block per record.

**Please don't hand-write JSON.** The real data files have interlocking id
references that are easy to get subtly wrong; conversion is quick and the
automated checks catch what the eye misses.

### Send a sample first

Send **5–10 events and 5–10 clubs** before doing the full collection. That is
enough to convert, run through the checks, and show you the finished cards. If
something about the shape is wrong, it costs ten records to find out instead of
two hundred.

### How much is enough

| Data | Minimum useful | UCSC has |
|---|---|---|
| Events | 10, spread across the days | 22 (6 confirmed) |
| Clubs | 20, spread across categories | 76 (35 confirmed) |
| Landmarks | 25 | 54 |
| Walking connections | 30 | 58 |

Coverage across days, categories, and interests matters more than raw count. An
interest button that matches nothing is a dead end, so aim for at least two or
three entries behind each of the six.

---

## 7. Blank templates to copy

### Event

```
Event name:
Date:
Time:
Location:
Description:
Who it's for:
Tags:
Confirmed?:
Source URL:
Date checked:
```

### Club

```
Club name:
Acronym / nicknames:
Category:
Description:
Tags:
Website:
Confirmed?:
Source URL:
Date checked:
```

### Landmark

```
Name:
Aliases:
Category:
Latitude:
Longitude:
Elevation (ft):
Sub-community:
Notes:
```

### Walking connection

```
From:
To:
Minutes:
Elevation change (ft):
Via:
Flags:
```

---

## Quick checklist before sending

- [ ] Every date is `YYYY-MM-DD` and inside the welcome week window
- [ ] No time is filled in that the school has not officially published
- [ ] No club contact or meeting time is filled in anywhere
- [ ] Every `Confirmed: YES` row has both a source URL and a check date
- [ ] No unconfirmed club carries a website
- [ ] Every event has 2–5 tags; every club has 3–6 and exactly one category
- [ ] All six interest buttons have at least two matching entries
- [ ] School header is filled in, including the involvement fair
