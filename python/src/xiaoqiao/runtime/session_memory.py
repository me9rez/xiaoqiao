"""Turn a finished session into a durable memory note.

This is a deterministic digest, not an LLM summary: it keeps the user's asks
from the latest turns so the next conversation can recall what happened.  It is
cheap, offline and testable; a model-based summary can replace it later without
changing the storage contract.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

MAX_ASKS = 5
MAX_CHARS = 400
PREFIX = "会话摘要："


def summarize_session(messages: Sequence[dict[str, Any]]) -> str | None:
    """Collect the recent user asks into a single short line."""
    asks: list[str] = []
    for message in messages:
        if str(message.get("role", "")) != "user":
            continue
        for content in message.get("contents", []) or []:
            if not isinstance(content, dict) or content.get("type") != "text":
                continue
            text = str(content.get("text", "")).strip()
            if text and (not asks or asks[-1] != text):
                asks.append(text)
    if not asks:
        return None
    joined = "；".join(asks[-MAX_ASKS:])
    if len(joined) > MAX_CHARS:
        joined = joined[: MAX_CHARS - 1].rstrip() + "…"
    return joined


def format_note(summary: str) -> str:
    return f"{PREFIX}{summary}"
