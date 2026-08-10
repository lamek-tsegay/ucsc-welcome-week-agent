# UCSC Welcome Week Agents

Three independent [uAgents](https://github.com/fetchai/uAgents) for **UC Santa Cruz
Slug Start / Fall Welcome Week**, Monday **Sept 21** – Saturday **Sept 26, 2026**.
Each runs locally, registers with [Agentverse](https://agentverse.ai) over a
mailbox, and is individually discoverable and callable from
[ASI:One](https://asi1.ai).

| Agent | Port | What it does | Output |
|---|---|---|---|
| **UCSC Campus Navigation** | 8021 | Walking directions, building lookup, what's nearby — with hill, stairs, and night awareness | Formatted text |
| **UCSC Welcome Week Events** | 8022 | Event recommendations by day, residential college, and interest | Interactive cards |
| **UCSC Clubs & Societies** | 8023 | Student organizations by interest or category | Interactive cards |

There is no orchestrator. Each agent publishes its own manifest and stands alone;
they cross-reference each other by name so ASI:One can chain them.

---

## Quickstart

**Python 3.10+ is required** — `uagents` will not install on older versions. If
your system `python3` is 3.9 (the macOS default), point the venv at a newer
interpreter explicitly.

```bash
cd ucsc-welcome-week

# Create the environment (substitute your 3.10+ interpreter)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# edit .env — see "Keys" below

# Verify everything works before going near the network.
# All four run with no API keys and no Agentverse account.
make test      # 168 unit tests, no network
make e2e       # in-process end-to-end across all 3 agents
make check     # data honesty gate
make live      # all 3 agents over real HTTP, driven by a real client uAgent
```

`make live` is the strongest offline check: it starts the three agents on
localhost endpoints, then drives them with an actual uAgent
(`scripts/chat_client.py`) sending signed envelopes over HTTP, tapping cards, and
asserting every message got a reply. It exercises envelope signing, transport,
protocol dispatch, and session handling — everything except the Agentverse
mailbox hop and ASI:One itself.

Then run each agent **in its own terminal**:

```bash
make nav       # UCSC Campus Navigation   :8021
make events    # UCSC Welcome Week Events :8022
make clubs     # UCSC Clubs & Societies   :8023
```

### Keys

| Variable | Needed for | If missing |
|---|---|---|
| `AGENTVERSE_API_KEY` | Publishing each agent's profile so ASI:One can discover it. Get one at [agentverse.ai/profile/api-keys](https://agentverse.ai/profile/api-keys) | Agents still run and answer anyone who knows their address, but stay undiscoverable |
| `ASI_ONE_API_KEY` | Natural-language parsing of unusual phrasings. Get one at [asi1.ai](https://asi1.ai) | **Everything still works.** Every agent has a deterministic keyword parser and only calls ASI:One when that comes up short |
| `NAVIGATION_SEED_PHRASE`, `EVENTS_SEED_PHRASE`, `CLUBS_SEED_PHRASE` | Agent identity | Falls back to the placeholder seeds in `.env.example` — fine for local testing, **change them before publishing anything you intend to keep** |

A seed phrase *is* the agent's permanent identity: its address is derived
deterministically from that string. Change a seed and you get a different agent
that nothing can find at the old address.

---

## Connecting to ASI:One

1. Start an agent. It logs an **Agent Inspector** URL.
2. Open that URL, sign in to Agentverse, and click **Connect** → **Mailbox**.
3. The agent appears in Agentverse under **Local Agents**. Confirm its manifest
   published.
4. Open [asi1.ai](https://asi1.ai), search for the agent by name, and chat.

Mailbox means the agent polls Agentverse for inbound messages, so no public IP,
port forwarding, or tunnel is needed. `mailbox=True` and `endpoint=[...]` are
mutually exclusive — setting both silently breaks chat delivery, so the choice
lives in one place, `common/transport.py`.

Setting `UCSC_LOCAL_ENDPOINT=1` swaps the mailbox for a plain `127.0.0.1`
endpoint. That is what `make live` uses to drive the agents locally without an
Agentverse account. It is a testing mode only — a localhost endpoint is not
reachable from ASI:One.

### Try these

**Navigation**
- *how do I get from Porter to McHenry Library*
- *where is Quarry Plaza*
- *route from Oakes to Science Hill avoiding hills*
- *step-free route from Cowell to the Bay Tree Bookstore*
- *from Porter to the Quarry Amphitheater at night*
- *what's near Crown College*

**Events**
- *what's happening Wednesday*
- *any events for Crown students*
- *free food this week*
- *outdoor stuff on Saturday*
- *show me the whole week* — then tap a card

**Clubs**
- *clubs about hiking*
- *I'm into anime*
- *show me cultural orgs*
- *anything for pre-med students*
- *what categories are there* — then tap a card

---

## Honesty about the data

These agents describe a real university, real dates, and real organizations,
built on **curated seed data**. A student who acts on a placeholder as though it
were the official schedule is worse off than one who got no answer. So the
labelling rules are enforced mechanically, not left to good intentions.

`make check` runs **357 assertions** over both the data files *and the rendered
output a student actually reads*.

### Events

Exactly **six event records across five date-lines are confirmed**, with dates
verified against the [official UCSC Slug Start
page](https://welcome.ucsc.edu/slug-life/fall-welcome-week/) on 2026-08-09:

| Day | Event |
|---|---|
| Mon Sept 21 | New Admit Class Photo (East Upper Field) · Late Night at Athletics & Rec |
| Tue Sept 22 | Cornucopia (East Upper Field) |
| Wed Sept 23 | Student Employment & Work-Study Fair |
| Fri Sept 25 | Boardwalk Frolic (Santa Cruz Beach Boardwalk) |
| Sat Sept 26 | Choose Your Own Slugventure |

**That page publishes dates but no times.** Every confirmed event therefore has
`time: null` and renders as *"time not yet published"* — never a guess. A test
fails if a `verified` event ever acquires a time.

The other 16 event records are **placeholder examples** to exercise filtering.
They carry `verified: false` and are labelled *unofficial* everywhere they appear.
Confirmed events also always sort above placeholders — that's the primary sort
key, so no relevance bonus can float a placeholder to the top.

The official page also notes that first-day programming **depends on your
residential college**, and colleges communicate that separately. The agent says so.

### Clubs

Two tiers. **35 engineering organizations are `verified: true`**: their existence
is confirmed against the official [Baskin Engineering student-organizations
page](https://undergrad.engineering.ucsc.edu/student-organizations/) (checked
2026-08-09, cited per-entry in `source`), including the club link that page
publishes. Everything else is **`verified: false`**: UCSC's general Registered
Student Organization directory is JS-rendered and "updated weekly in the fall as
organizations complete basic registration", so it cannot be confirmed from a
static read — those entries are representative examples of the *categories* of
organizations UCSC has, and are labelled unofficial everywhere they appear.

`contact` and `meeting_info` are `null` for every entry, deliberately. A wrong
email address sends a student to the wrong place, which is worse than no address.
The agent points at [the official
directory](https://getinvolved.ucsc.edu/student-organizations/join/),
`soar@ucsc.edu`, and Cornucopia instead. A test fails if any email address other
than the official SOAR contact ever appears in output.

### Navigation

Coordinates and walking times are **hand-curated estimates**, adequate for
relative positioning and routing, not survey-grade — and presented as estimates.
Transit routes are approximate and marked unverified, with frequencies and
operating hours omitted rather than guessed; the agent links to
[scmtd.com](https://scmtd.com). Accessibility flags are incomplete, and
step-free routing says so and refers users to the Disability Resource Center.

---

## Architecture

```
ucsc-welcome-week/
├── common/            # shared across all three agents
│   ├── loader.py      # the data seam — the only module that touches files
│   ├── chat.py        # ack helper, text messages, card-selection parsing
│   ├── cards.py       # generic ASI:One element-tree card builders
│   ├── asi1.py        # ASI:One client; returns None on any failure
│   ├── guard.py       # echo-loop, duplicate, and cooldown defences
│   ├── notices.py     # the single implementation of verification labelling
│   └── registration.py# Agentverse registration
├── data/
│   ├── landmarks.json # 54 campus locations
│   ├── walk_graph.json# 58 undirected edges with minutes, elevation, flags
│   ├── transit.json   # approximate bus/shuttle routes
│   ├── events.json    # 22 events, 6 confirmed
│   └── clubs.json     # 76 organizations; 35 confirmed engineering orgs
├── agents/
│   ├── navigation/    # resolve → parse → router → render → service → agent
│   ├── events/        # recommend → cards → service → agent
│   └── clubs/         # search → cards → service → agent
├── scripts/
│   ├── local_test.py  # in-process E2E, no network
│   ├── chat_client.py # real client uAgent, drives the agents over HTTP
│   ├── live_test.sh   # orchestrates `make live`
│   └── honesty_check.py
└── tests/             # 168 unit tests
```

Two patterns worth knowing if you extend this:

**`service.py` is separate from `agent.py` in every agent.** The service holds all
query logic and imports nothing from uAgents transport; the agent holds the
protocol handlers. Tests exercise services without constructing an `Agent` (which
would bind a port and schedule manifest publication).

**`common/loader.py` is the only module that reads files.** Replacing the seed
data with real UCSC exports means changing loaders, not agent logic.

### Per-agent request flow

Every agent follows the same shape, taken from
`innovation-lab-examples/av-script-example/agent.py`:

1. Send `ChatAcknowledgement` **first**, before any work
2. `StartSessionContent` → welcome text
3. Card tap (`MetadataContent` selection arriving as text) → detail card,
   **bypassing the echo guard**, since tapping the same card twice is legitimate
4. Otherwise → echo guard, then the service, then reply
5. Register a `ChatAcknowledgement` handler even as a no-op — without it the
   published manifest is incomplete

### Echo-loop defence

ASI:One's chat UI can take an agent's reply, rewrite it, and resend it as a fresh
user objective, which loops a naive agent. `common/guard.py` handles this three
ways: fuzzy matching of inbound text against what we recently *sent* (the real
defence — echoes come back reworded), a short inbound dedup window, and a
per-sender cooldown.

Calibration matters here, and getting it wrong is its own bug: **every
suppression is silent**, so an over-eager guard is indistinguishable from a
broken agent. The live test caught exactly that — an early 1.5s blanket cooldown
was dropping distinct, legitimate questions asked in quick succession. The
settled values:

| Mechanism | Window | Why |
|---|---|---|
| Echo detection | 300s | Precise (compares against what we actually sent), so it can afford a long memory. The real loop defence. |
| Inbound dedup | 15s | Absorbs double-sends. Someone re-asking a minute later is a human wanting an answer. |
| Cooldown | 0.3s | Only absorbs instantaneous double-delivery. Does **not** rate-limit a person asking several different things quickly. |
| Burst limit | 12 per 10s | Last-resort circuit breaker for a loop whose wording varies too much for echo detection. No real conversation reaches it. |

---

## Versions

Pinned to `uagents==0.23.6` + `uagents-core==0.4.0` — the combination the Fetch.ai
deployment docs actually validate. Version pinning across
`innovation-lab-examples` is fragmented (`uagents` pins there range from
`>=0.4.0` to `==0.24.0`); this is the pair that works together.

Do not use `innovation-lab-examples/cursor-rules/fetchai.mdc` as a reference — it
pins `uagents==0.22.5` and recommends a rate-limited LLM-proxy-agent pattern that
direct ASI:One API keys have superseded.

---

## Limitations

**These agents answer on ASI:One only while running on your machine.** That is
what local-mailbox deployment means. It is right for building and demoing; it is
not enough if students are meant to rely on them during Sept 21–26. Before then,
promote each agent to always-on hosting — a Render **Background Worker** with
`python -m agents.<name>.agent` as the start command works, per
`innovation-lab-examples/deploy-agent-on-av/docs.md`.

**Set `UCSC_TODAY_OVERRIDE=2026-09-22`** in `.env` to demo relative date handling
("tonight", "tomorrow") as though it were Welcome Week, without touching your
system clock.

**The seed data is the weak point, not the code.** Getting real data in is the
highest-value next step:

- **Events** — the real per-college schedules, and times once published
- **Clubs** — a SOAR/SOMeCA directory export (`soar@ucsc.edu`)
- **Navigation** — official building coordinates and accessible-path data

Each drops into `data/` behind `common/loader.py` with no agent changes. Keep the
`verified` flags accurate when you do: flip `verified: true` only for records you
actually confirmed, and the honesty gate will hold you to the rest.
