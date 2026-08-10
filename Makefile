.PHONY: install nav events clubs test e2e check live

# Use the project venv directly so no target depends on activation.
PY ?= .venv/bin/python

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

# Each agent is an independent process. Run each in its own terminal, then open
# the Agent Inspector URL it logs to connect its Agentverse mailbox.
nav:
	$(PY) -m agents.navigation.agent

events:
	$(PY) -m agents.events.agent

clubs:
	$(PY) -m agents.clubs.agent

# Pure-logic unit tests. No network, no running agents.
test:
	$(PY) -m pytest -q

# In-process end-to-end: drives each chat handler with synthetic ChatMessages.
e2e:
	$(PY) -m scripts.local_test

# Data honesty gate: fails if any unverified record would be presented as official.
check:
	$(PY) -m scripts.honesty_check

# Live test: starts all three agents on localhost endpoints, drives them with a
# real client uAgent over HTTP, then shuts everything down. No API keys needed.
live:
	@bash scripts/live_test.sh
