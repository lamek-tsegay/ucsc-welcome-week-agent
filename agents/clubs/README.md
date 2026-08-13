# clubs agent

- `agent.py` — entrypoint: identity, transport, Agentverse registration.
- `protocols/chat_proto.py` — the conversation: ack-first, replay/echo/prose
  defences, card-tap routing.
- Everything campus-specific (copy, links, vibes, data) lives in
  `campuses/<CAMPUS_ID>/`, not here.

Run from the repo root: `.venv/bin/python -m agents.clubs.agent`
Build: `docker build -f agents/clubs/Dockerfile .` (repo-root context).
