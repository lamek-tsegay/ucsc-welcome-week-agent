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

import asyncio
import re
import time
from dataclasses import dataclass, field

# How long a message we have already answered is held to see whether a newer
# one is right behind it. Replayed history arrives in an immediate burst, so
# this only has to outlast the gap between messages in one delivery.
REPLAY_HOLD_SECONDS = 1.5

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
    answered_memory_seconds: float = 1800.0

    _inbound: dict[tuple[str, str], float] = field(default_factory=dict)
    _last_handled: dict[str, float] = field(default_factory=dict)
    _outbound: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    _handled_at: dict[str, list[float]] = field(default_factory=dict)
    _seq: dict[str, int] = field(default_factory=dict)
    _answered: dict[str, dict[str, float]] = field(default_factory=dict)

    def _now(self, now: float | None) -> float:
        return time.monotonic() if now is None else now

    # --- conversation replay -------------------------------------------------
    #
    # ASI:One re-sends the whole conversation on every turn: tapping one button
    # delivers the original question and every earlier tap alongside the new
    # one. Answering all of them means several round trips per tap, and the
    # card the student actually asked for arrives last.
    #
    # The messages cannot simply be suppressed on sight. A replayed message and
    # a deliberate repeat are byte-identical — the only thing that separates
    # them is what happens next: a replay is always followed immediately by the
    # newer message it was bundled with, while a repeat arrives alone. So a
    # message we have already answered is held briefly, and dropped only if
    # something newer turns up while it waits. That costs a short delay on
    # genuine repeats and nothing at all on new messages, which are the common
    # case, and it never answers with silence.

    def note_inbound(self, sender: str) -> int:
        """Record that a message arrived. Returns its per-sender sequence."""
        self._seq[sender] = self._seq.get(sender, 0) + 1
        return self._seq[sender]

    def is_newest(self, sender: str, sequence: int) -> bool:
        """True if nothing has arrived from this sender since `sequence`."""
        return self._seq.get(sender, 0) == sequence

    def already_answered(
        self, sender: str, text: str, *, now: float | None = None
    ) -> bool:
        """Whether this exact message has been answered recently."""
        moment = self._now(now)
        seen = self._answered.get(sender, {}).get(normalise(text))
        return seen is not None and moment - seen <= self.answered_memory_seconds

    def mark_answered(self, sender: str, text: str, *, now: float | None = None) -> None:
        moment = self._now(now)
        answered = self._answered.setdefault(sender, {})
        answered[normalise(text)] = moment
        for key, when in list(answered.items()):
            if moment - when > self.answered_memory_seconds:
                del answered[key]

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
        self._seq.clear()
        self._answered.clear()

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


async def is_stale_replay(
    guard: EchoGuard,
    sender: str,
    text: str,
    sequence: int,
    *,
    hold: float = REPLAY_HOLD_SECONDS,
) -> bool:
    """True when this message is replayed history and should be dropped.

    Call after `guard.note_inbound(sender)` and before doing any work. A
    message the agent has not answered before returns immediately, so the
    common path costs nothing. One it has answered is held for `hold` seconds;
    if something newer arrives meanwhile it was part of a replayed batch and
    is dropped, otherwise it is a deliberate repeat and gets answered.
    """
    if not guard.already_answered(sender, text):
        return False
    await asyncio.sleep(hold)
    return not guard.is_newest(sender, sequence)
