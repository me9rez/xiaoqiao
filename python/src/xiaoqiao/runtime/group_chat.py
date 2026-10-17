"""Group chat orchestration: message in, bot replies out, bounded handoffs.

This is deliberately *not* a multi-agent planner.  A user message is routed by
``@`` mentions, each selected bot answers independently, and a bot can hand off
to another by mentioning it.  Hop count, per-turn bot count and cooldown are
enforced here so two bots cannot talk forever.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from xiaoqiao.router import HopPolicy, can_trigger, parse_mentions, resolve_recipients
from xiaoqiao.runtime.group_messages import GroupMessage, GroupMessageRepository

if TYPE_CHECKING:
    from xiaoqiao.bots import Bot, BotRepository
    from xiaoqiao.groups import GroupRepository
    from xiaoqiao.runtime.sessions import SessionRecord, SessionRepository

logger = logging.getLogger(__name__)

ExecuteBot = Callable[["Bot", "SessionRecord", list[GroupMessage]], Awaitable[str]]


def render_group_context(bot: Bot, messages: list[GroupMessage], names: dict[str, str]) -> str:
    """Render new group messages as a prompt block for one bot.

    Other bots' messages are labelled with their name; the bot's own messages
    are labelled ``你`` so it can keep its own voice without confusing itself
    with a participant.
    """
    lines = ["以下是群聊中你需要回应的新消息（按时间顺序）："]
    for message in messages:
        if message.author_type == "user":
            author = "用户"
        elif message.author_type == "system":
            author = "系统"
        else:
            author = "你" if message.author_id == bot.id else names.get(message.author_id, "另一个 Bot")
        lines.append(f"[{author}] {message.text}")
    lines.append("")
    lines.append("请直接给出你的回复；如果你需要另一位 Bot 接着处理，可以在回复里 @ 对方。")
    return "\n".join(lines)


@dataclass
class _Pending:
    bot_id: str
    hop: int
    reply_to: str
    last_speaker: str | None


class GroupChatService:
    """Routes one user message through the group and collects replies."""

    def __init__(
        self,
        bots: BotRepository,
        groups: GroupRepository,
        sessions: SessionRepository,
        messages: GroupMessageRepository,
        *,
        policy: HopPolicy | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._bots = bots
        self._groups = groups
        self._sessions = sessions
        self._messages = messages
        self._policy = policy or HopPolicy()
        self._now = now or (lambda: datetime.now(UTC))
        self._last_run_at: dict[str, datetime] = {}

    async def handle_user_message(self, group_id: str, text: str, execute: ExecuteBot) -> list[GroupMessage]:
        group = self._groups.get(group_id)
        if group is None:
            raise ValueError(f"unknown group: {group_id}")
        if group.archived:
            raise ValueError(f"group is archived: {group_id}")

        bots = [bot for bot_id in group.bot_ids if (bot := self._bots.get(bot_id)) is not None]
        if not bots:
            raise ValueError(f"group has no bots: {group_id}")

        max_bots = int(group.settings.get("maxBotsPerTurn", self._policy.max_bots_per_turn))
        decision = resolve_recipients(text, bots, group.default_bot_id, max_bots=max_bots)
        user_message = self._messages.append(
            group.id,
            author_type="user",
            author_id="owner",
            text=text,
            mentions=decision.recipients,
        )
        appended = [user_message]
        if not decision.recipients:
            return appended

        queue = [_Pending(bot_id, 0, user_message.id, None) for bot_id in decision.recipients]
        skipped: dict[str, str] = {}
        hop_notice_sent = False

        while queue:
            item = queue.pop(0)
            bot = next((candidate for candidate in bots if candidate.id == item.bot_id), None)
            if bot is None:
                continue

            allowed, reason = can_trigger(
                hop=item.hop,
                bot_id=bot.id,
                policy=self._policy,
                last_speaker_id=item.last_speaker,
                last_run_at=self._last_run_at.get(bot.id),
                now=self._now(),
            )
            if not allowed:
                skipped[bot.name] = reason
                continue

            session = self._sessions.get_or_create(bot.id, group_id=group.id)
            new_messages = self._messages.since(group.id, session.last_seen_seq)
            try:
                reply = (await execute(bot, session, new_messages) or "").strip()
            except Exception:
                logger.exception("Bot %s failed in group %s", bot.id, group.id)
                appended.append(
                    self._messages.append(
                        group.id,
                        author_type="system",
                        author_id="system",
                        text=f"{bot.name} 执行失败，已跳过。",
                        reply_to=item.reply_to,
                    )
                )
                continue

            if not reply:
                continue

            mentioned, mentions_all, _ = parse_mentions(reply, bots)
            targets = [candidate for candidate in bots if candidate.id in set(mentioned)]
            if mentions_all:
                targets = [candidate for candidate in bots if candidate.id != bot.id]
            targets = [candidate for candidate in targets if candidate.id != bot.id][:max_bots]

            reply_message = self._messages.append(
                group.id,
                author_type="bot",
                author_id=bot.id,
                text=reply,
                mentions=[candidate.id for candidate in targets],
                reply_to=item.reply_to,
            )
            appended.append(reply_message)
            self._sessions.update(session.id, last_seen_seq=reply_message.seq)
            self._last_run_at[bot.id] = self._now()

            if not targets:
                continue
            next_hop = item.hop + 1
            if next_hop > self._policy.max_hops:
                if not hop_notice_sent:
                    hop_notice_sent = True
                    appended.append(
                        self._messages.append(
                            group.id,
                            author_type="system",
                            author_id="system",
                            text=f"已达到 {self._policy.max_hops} 跳上限，继续对话请手动 @。",
                            reply_to=reply_message.id,
                        )
                    )
                continue
            for target in targets:
                queue.append(_Pending(target.id, next_hop, reply_message.id, bot.id))

        if skipped:
            detail = "、".join(f"{name}（{reason}）" for name, reason in skipped.items())
            appended.append(
                self._messages.append(
                    group.id,
                    author_type="system",
                    author_id="system",
                    text=f"部分 Bot 未响应：{detail}",
                    reply_to=user_message.id,
                )
            )
        return appended
