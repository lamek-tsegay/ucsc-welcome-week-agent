"""ASI:One LLM client.

ASI:One exposes an OpenAI-compatible endpoint, so the official `openai` SDK
works against it unchanged — only `base_url` differs.

Every function here returns None on any failure (missing key, network error,
unparseable output) rather than raising. That is deliberate: the LLM is an
enhancement in this system, never a dependency. Each agent pairs its LLM call
with a deterministic fallback parser, so all three agents remain fully
functional with no ASI_ONE_API_KEY set at all.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.asi1.ai/v1"
DEFAULT_MODEL = os.getenv("ASI_ONE_MODEL", "asi1-mini")
REQUEST_TIMEOUT_SECONDS = 20.0

_logger = logging.getLogger(__name__)
_client: Any = None
_client_attempted = False


def api_key() -> str | None:
    return os.getenv("ASI_ONE_API_KEY") or None


def is_enabled() -> bool:
    """True if an ASI:One key is configured. Agents branch on this."""
    return api_key() is not None


def _get_client() -> Any:
    """Lazily build the async client. Returns None if unavailable."""
    global _client, _client_attempted
    if _client_attempted:
        return _client
    _client_attempted = True

    key = api_key()
    if not key:
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError:
        _logger.warning("openai package not installed; ASI:One calls disabled")
        return None

    _client = AsyncOpenAI(
        base_url=BASE_URL, api_key=key, timeout=REQUEST_TIMEOUT_SECONDS
    )
    return _client


async def _complete(
    *, system: str, user: str, max_tokens: int, temperature: float
) -> str | None:
    client = _get_client()
    if client is None:
        return None

    try:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception:
        _logger.exception("ASI:One request failed")
        return None

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError):
        _logger.warning("ASI:One returned an unexpected response shape")
        return None

    return content.strip() if content else None


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


async def structured(
    *, system: str, user: str, max_tokens: int = 400
) -> dict[str, Any] | None:
    """Ask for JSON and parse it. None if anything goes wrong.

    Models wrap JSON in prose or fences often enough that we extract the first
    balanced-looking object rather than trusting the whole response to parse.
    """
    raw = await _complete(
        system=system, user=user, max_tokens=max_tokens, temperature=0.0
    )
    if not raw:
        return None

    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        # Drop a leading language tag such as "json\n".
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(candidate)
        if not match:
            _logger.warning("ASI:One structured call returned no JSON object")
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            _logger.warning("ASI:One structured call returned malformed JSON")
            return None

    return parsed if isinstance(parsed, dict) else None


async def prose(*, system: str, user: str, max_tokens: int = 220) -> str | None:
    """Ask for a short piece of natural-language text. None on failure."""
    return await _complete(
        system=system, user=user, max_tokens=max_tokens, temperature=0.4
    )
