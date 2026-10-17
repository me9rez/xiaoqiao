"""Context window compaction — summarize old messages to stay within token budget."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_DEFAULT_MAX_TOKENS = 128_000
_DEFAULT_KEEP_RECENT = 8_000


def estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def should_compact(messages: list[object], max_tokens: int = _DEFAULT_MAX_TOKENS) -> bool:
    total = 0
    for msg in messages:
        text = getattr(msg, "text", "") or ""
        total += estimate_tokens(text)
    return total > max_tokens * 0.75


async def compact_messages(
    messages: list[object],
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    keep_recent_tokens: int = _DEFAULT_KEEP_RECENT,
) -> list[object]:
    if not should_compact(messages, max_tokens):
        return messages

    try:
        from agent_framework._compaction import ContextWindowCompactionStrategy, apply_compaction

        strategy = ContextWindowCompactionStrategy(
            max_context_window_tokens=max_tokens,
            max_output_tokens=keep_recent_tokens,
        )
        compacted: list[object] = await apply_compaction(messages, strategy=strategy)  # type: ignore[arg-type]
        logger.info("Compacted %d -> %d messages", len(messages), len(compacted))
        return compacted
    except ImportError:
        logger.debug("Strategy not available, using simple truncation")
    except Exception as exc:
        logger.warning("Compaction failed: %s", exc)

    return _simple_truncation(messages, max_tokens, keep_recent_tokens)  # type: ignore[arg-type]


def _simple_truncation(
    messages: list[object],
    max_tokens: int,
    keep_recent_tokens: int,
) -> list[object]:
    total = sum(estimate_tokens(getattr(m, "text", "") or "") for m in messages)
    if total <= max_tokens:
        return messages

    kept: list[object] = []
    recent_tokens = 0
    for msg in reversed(messages):
        text = getattr(msg, "text", "") or ""
        tokens = estimate_tokens(text)
        if recent_tokens + tokens > keep_recent_tokens and len(kept) > 1:
            break
        kept.insert(0, msg)
        recent_tokens += tokens

    if messages and getattr(messages[0], "role", "") == "system" and kept[0] is not messages[0]:
        kept.insert(0, messages[0])

    logger.info("Truncated %d -> %d messages (%d tok)", len(messages), len(kept), recent_tokens)
    return kept
