"""Quoted replies: attaching "this answers that message" to a stored turn.

The framework's ``AgentSession`` owns the transcript, and the user message is built
inside ``agent.run()`` — there is no hook to hand it extra fields.  So the quote is
attached to the already-stored user message *after* the run, in its
``additional_properties`` (the same bag ``thinking`` historically used).  That keeps
one transcript, no parallel table, and survives a reload.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Longest quote we keep; a quote is a pointer, not a second copy of the message.
MAX_QUOTE_CHARS = 200


def quote_param(raw: Any) -> dict[str, str] | None:
    """Normalise an RPC ``quoted`` argument, or ``None`` when there is nothing usable."""
    if not isinstance(raw, dict):
        return None
    author = str(raw.get("authorName") or "").strip()
    text = str(raw.get("text") or "").strip()
    if not author and not text:
        return None
    return {
        "authorName": author or "未署名",
        "text": text[:MAX_QUOTE_CHARS],
    }


def attach_quote(messages: list[Any], quote: dict[str, str]) -> bool:
    """Attach *quote* to the last user message. Returns whether it found one.

    Messages are the dicts the session persists (``save_session`` json-dumps them),
    but tolerate objects that expose ``additional_properties`` so the helper stays
    usable from tests that build pydantic messages.
    """
    for message in reversed(messages):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        if role != "user":
            continue
        if isinstance(message, dict):
            properties = message.get("additional_properties")
            if not isinstance(properties, dict):
                properties = {}
                message["additional_properties"] = properties
            properties["quoted"] = dict(quote)
            return True
        properties = getattr(message, "additional_properties", None)
        if isinstance(properties, dict):
            properties["quoted"] = dict(quote)
            return True
        logger.debug("Cannot attach quote: message has no additional_properties")
        return False
    logger.debug("Cannot attach quote: no user message in transcript")
    return False


__all__ = ["MAX_QUOTE_CHARS", "attach_quote", "quote_param"]
