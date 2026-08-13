"""Test-suite-wide isolation from the network.

The agents call ASI:One only as a fallback, and `common/asi1.py` degrades to None
on any failure — so the suite passes with or without a key configured. But it
does not produce the *same* answers either way: with a key present, a query the
deterministic parser rejects gets a second, non-deterministic opinion from a
live model.

That makes the suite depend on whether the developer happens to have a `.env`,
which is the opposite of what a unit test should do. The fixture below clears
the key for every test, so the suite always exercises the deterministic path and
never touches the network.

Tests that want to assert on ASI:One behaviour should stub `common.asi1`
explicitly rather than relying on a real key being present.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_profiles(monkeypatch, tmp_path):
    """Point the shared profile store at a per-test scratch file.

    Without this, tests that save a college or star an event would write the
    developer's real .profiles.json — state leaking between tests and runs.
    """
    monkeypatch.setenv("UCSC_PROFILE_PATH", str(tmp_path / "profiles.json"))


@pytest.fixture(autouse=True)
def _disable_asi1(monkeypatch):
    """Force the deterministic path for every test, regardless of local .env."""
    monkeypatch.delenv("ASI_ONE_API_KEY", raising=False)

    # common.asi1 caches its client across calls, so clearing the env var alone
    # is not enough once something has already built one.
    from agents_shared import asi1

    monkeypatch.setattr(asi1, "_client", None, raising=False)
    monkeypatch.setattr(asi1, "_client_attempted", False, raising=False)
