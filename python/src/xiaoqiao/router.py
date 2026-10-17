"""Deterministic @ routing for group chats.

The router decides *who should answer* a message.  It never talks to the LLM
and never orchestrates a task: mentions in, recipients out.  Loop protection
lives here too, because it is the only place that knows the hop of a run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from xiaoqiao.bots import Bot

_MENTION_RE = re.compile(r"@([^\s@，,。.;；:：]+)")
_ALL = "all"


@dataclass(frozen=True)
class RouteDecision:
    """Recipients for one group message, plus why they were chosen."""

    recipients: tuple[str, ...]
    reason: str  # mention | all | default | fallback | empty
    unknown: tuple[str, ...] = ()
    truncated: bool = False


def parse_mentions(text: str, bots: Sequence[Bot]) -> tuple[list[str], bool, list[str]]:
    """Return ``(bot_ids, mentions_all, unknown_tokens)`` for a message."""
    by_key: dict[str, str] = {}
    for bot in bots:
        by_key[bot.slug.lower()] = bot.id
        by_key[bot.name.lower()] = bot.id

    recipients: list[str] = []
    unknown: list[str] = []
    mentions_all = False
    for token in _MENTION_RE.findall(text or ""):
        key = token.lower()
        if key == _ALL:
            mentions_all = True
            continue
        bot_id = by_key.get(key)
        if bot_id is None:
            unknown.append(token)
        elif bot_id not in recipients:
            recipients.append(bot_id)
    return recipients, mentions_all, unknown


def resolve_recipients(
    text: str,
    bots: Sequence[Bot],
    default_bot_id: str | None = None,
    *,
    max_bots: int = 3,
) -> RouteDecision:
    """Map a group message to the bots that should answer it."""
    if not bots:
        return RouteDecision(recipients=(), reason="empty")

    mentioned, mentions_all, unknown = parse_mentions(text, bots)
    if mentions_all:
        recipients = [bot.id for bot in bots]
        reason = "all"
    elif mentioned:
        recipients = mentioned
        reason = "mention"
    elif unknown and default_bot_id:
        recipients = [default_bot_id]
        reason = "fallback"
    else:
        fallback = default_bot_id or bots[0].id
        recipients = [fallback]
        reason = "default"

    truncated = len(recipients) > max_bots
    return RouteDecision(
        recipients=tuple(recipients[:max_bots]),
        reason=reason,
        unknown=tuple(unknown),
        truncated=truncated,
    )


@dataclass(frozen=True)
class HopPolicy:
    """Hard limits that keep bots from talking to each other forever."""

    max_hops: int = 3
    max_bots_per_turn: int = 3
    cooldown_seconds: float = 2.0


def can_trigger(
    *,
    hop: int,
    bot_id: str,
    policy: HopPolicy | None = None,
    last_speaker_id: str | None = None,
    last_run_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for a bot-to-bot hop."""
    policy = policy or HopPolicy()
    if hop > policy.max_hops:
        return False, "hop_limit"
    if last_speaker_id is not None and bot_id == last_speaker_id:
        return False, "self_repeat"
    if last_run_at is not None:
        reference = now or datetime.now(last_run_at.tzinfo)
        if reference - last_run_at < timedelta(seconds=policy.cooldown_seconds):
            return False, "cooldown"
    return True, "allowed"


def filter_triggerable(
    bot_ids: Iterable[str],
    *,
    hop: int,
    policy: HopPolicy | None = None,
    last_speaker_id: str | None = None,
    last_run_at: dict[str, datetime] | None = None,
    now: datetime | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Split candidates into allowed ids and ``rejected`` id -> reason."""
    policy = policy or HopPolicy()
    allowed: list[str] = []
    rejected: dict[str, str] = {}
    seen_runs = last_run_at or {}
    for bot_id in bot_ids:
        ok, reason = can_trigger(
            hop=hop,
            bot_id=bot_id,
            policy=policy,
            last_speaker_id=last_speaker_id,
            last_run_at=seen_runs.get(bot_id),
            now=now,
        )
        if ok:
            allowed.append(bot_id)
        else:
            rejected[bot_id] = reason
    return allowed, rejected
