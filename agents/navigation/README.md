# navigation agent

- `agent.py` — entrypoint: identity, transport, Agentverse registration.
- `protocols/chat_proto.py` — the conversation: ack-first, replay/echo/prose
  defences, card-tap routing.
- Everything campus-specific (copy, links, vibes, data) lives in
  `campuses/<CAMPUS_ID>/`, not here.

Run from the repo root: `.venv/bin/python -m agents.navigation.agent`
Build: `docker build -f agents/navigation/Dockerfile .` (repo-root context).
