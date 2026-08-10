"""Echo-loop and duplicate-message defence.

ASI:One's chat UI can take an agent's own reply, rewrite it, and resend it as a
fresh user objective. An agent that answers everything it receives will then talk
to itself, sometimes indefinitely. The mitigations here are the ones the
openclaw example documents, packaged for reuse:

1. **Echo suppression** — remember what we sent to each sender; ignore inbound
   text that closely matches a recent outbound.
2. **Inbound dedup** — ignore the same inbound text from the same sender twice
   inside a window.
3. **Per-sender cooldown** — ignore anything arriving faster than a human could
   plausibly send it.

Time is injectable so this is testable without sleeping.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_NORMALISE_RE = re.compile(r"[^a-z0-9 ]+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Loose on purpose: ASI:One rewrites wording slightly when it echoes, so exact
    matching would miss real echoes.
    """
    lowered = text.strip().lower()
    lowered = _NORMALISE_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def _similar(a: str, b: str, *, threshold: float = 0.85) -> bool:
    """Token-overlap similarity (Jaccard). Cheap and good enough for echoes."""
    if not a or not b:
        return False
    if a == b:
        return True
    tokens_a, tokens_b = set(a.split()), set(b.split())
    if not tokens_a or not tokens_b:
        return False
    overlap = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    return overlap >= threshold


@dataclass
class EchoGuard:
    """Decides whether an inbound message deserves a reply.

    Window sizing matters more than it looks, and getting it wrong is its own bug:
    every suppression is silent, so an over-eager guard looks to the student
    exactly like a broken agent.

    - **Echo detection** compares inbound text against what we actually sent. It
      is precise, so it can afford a long memory. This is the real loop defence.
    - **Inbound dedup** is a safety net against double-sends and retries, so its
      window is short. Someone re-asking a minute later is a human wanting an
      answer, not a loop.
    - **Cooldown** exists only to absorb instantaneous double-delivery, so it is
      a fraction of a second. It deliberately does *not* rate-limit a person
      asking several different questions quickly — distinct questions always get
      answered.
    - **Burst limiting** is the last-resort circuit breaker for a runaway loop
      whose wording varies too much for echo detection to catch. The ceiling is
      generous enough that no real conversation reaches it.
    """

    dedup_window_seconds: float = 15.0
    cooldown_seconds: float = 0.3
    outbound_memory_seconds: float = 300.0
    max_outbound_per_sender: int = 12
    max_burst: int = 12
    burst_window_seconds: float = 10.0

    _inbound: dict[tuple[str, str], float] = field(default_factory=dict)
    _last_handled: dict[str, float] = field(default_factory=dict)
    _outbound: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    _handled_at: dict[str, list[float]] = field(default_factory=dict)

    def _now(self, now: float | None) -> float:
        return time.monotonic() if now is None else now

    def note_outbound(self, sender: str, text: str, *, now: float | None = None) -> None:
        """Record text we sent, so we can recognise it if it comes back."""
        moment = self._now(now)
        history = self._outbound.setdefault(sender, [])
        history.append((normalise(text), moment))
        # Keep the list bounded and drop entries too old to matter.
        fresh = [
            entry
            for entry in history[-self.max_outbound_per_sender :]
            if moment - entry[1] <= self.outbound_memory_seconds
        ]
        self._outbound[sender] = fresh

    def classify(self, sender: str, text: str, *, now: float | None = None) -> str | None:
        """Return the reason to suppress, or None to proceed.

        Reasons: "empty", "cooldown", "duplicate", "echo", "flood".
        """
        moment = self._now(now)
        cleaned = normalise(text)
        if not cleaned:
            return "empty"

        last = self._last_handled.get(sender)
        if last is not None and moment - last < self.cooldown_seconds:
            return "cooldown"

        seen = self._inbound.get((sender, cleaned))
        if seen is not None and moment - seen <= self.dedup_window_seconds:
            return "duplicate"

        for previous, sent_at in self._outbound.get(sender, []):
            if moment - sent_at > self.outbound_memory_seconds:
                continue
            if _similar(cleaned, previous):
                return "echo"

        recent = [
            stamp
            for stamp in self._handled_at.get(sender, [])
            if moment - stamp <= self.burst_window_seconds
        ]
        if len(recent) >= self.max_burst:
            return "flood"

        return None

    def should_handle(self, sender: str, text: str, *, now: float | None = None) -> bool:
        """True if we should act on this message. Records it when True."""
        moment = self._now(now)
        if self.classify(sender, text, now=moment) is not None:
            return False

        self._inbound[(sender, normalise(text))] = moment
        self._last_handled[sender] = moment
        self._handled_at.setdefault(sender, []).append(moment)
        self._prune(moment)
        return True

    def reset(self) -> None:
        """Forget everything. Used to isolate tests from each other."""
        self._inbound.clear()
        self._last_handled.clear()
        self._outbound.clear()
        self._handled_at.clear()

    def _prune(self, moment: float) -> None:
        stale = [
            key
            for key, seen in self._inbound.items()
            if moment - seen > self.dedup_window_seconds
        ]
        for key in stale:
            del self._inbound[key]

        for sender, stamps in list(self._handled_at.items()):
            fresh = [
                stamp for stamp in stamps if moment - stamp <= self.burst_window_seconds
            ]
            if fresh:
                self._handled_at[sender] = fresh
            else:
                del self._handled_at[sender]
