"""Unit tests for group routing, handoffs and loop limits."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.groups import GroupRepository
from xiaoqiao.router import HopPolicy
from xiaoqiao.runtime.group_chat import GroupChatService, render_group_context
from xiaoqiao.runtime.group_messages import GroupMessageRepository
from xiaoqiao.runtime.sessions import SessionRepository

if TYPE_CHECKING:
    from xiaoqiao.bots import Bot
    from xiaoqiao.runtime.group_messages import GroupMessage
    from xiaoqiao.runtime.sessions import SessionRecord

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        self.bots = BotRepository(db)
        self.groups = GroupRepository(db)
        self.sessions = SessionRepository(db)
        self.messages = GroupMessageRepository(db)
        self.coder = self.bots.create("Coder", slug="coder")
        self.watch = self.bots.create("盯盘", slug="watch")
        self.life = self.bots.create("生活助理", slug="life")
        self.group = self.groups.create(
            "Daily",
            [self.coder.id, self.watch.id, self.life.id],
            default_bot_id=self.coder.id,
            settings={"maxHops": 2, "maxBotsPerTurn": 3},
        )
        self.calls: list[tuple[str, list[str]]] = []

    def service(self, *, max_hops: int = 2) -> GroupChatService:
        return GroupChatService(
            self.bots,
            self.groups,
            self.sessions,
            self.messages,
            policy=HopPolicy(max_hops=max_hops, max_bots_per_turn=3, cooldown_seconds=0),
            now=lambda: NOW,
        )

    def responder(self, replies: dict[str, str]):
        async def execute(bot: Bot, session: SessionRecord, messages: list[GroupMessage]) -> str:
            self.calls.append((bot.slug, [message.text for message in messages]))
            return replies.get(bot.slug, f"{bot.name} 收到")

        return execute


class TestRenderContext:
    def test_labels_authors_and_self(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        messages = [
            harness.messages.append(harness.group.id, author_type="user", author_id="owner", text="查行情"),
            harness.messages.append(harness.group.id, author_type="bot", author_id=harness.watch.id, text="在查"),
            harness.messages.append(harness.group.id, author_type="bot", author_id=harness.coder.id, text="收到"),
        ]

        rendered = render_group_context(
            harness.coder,
            messages,
            {harness.watch.id: "盯盘", harness.coder.id: "Coder"},
        )

        assert "[用户] 查行情" in rendered
        assert "[盯盘] 在查" in rendered
        assert "[你] 收到" in rendered
        assert "@ 对方" in rendered


class TestRouting:
    @pytest.mark.asyncio
    async def test_mentions_only_the_addressed_bot(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        chat = harness.service()

        appended = await chat.handle_user_message(harness.group.id, "@watch 查行情", harness.responder({}))

        assert [call[0] for call in harness.calls] == ["watch"]
        assert [m.author_type for m in appended] == ["user", "bot"]
        assert appended[1].text == "盯盘 收到"

    @pytest.mark.asyncio
    async def test_without_mention_uses_default_bot(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        chat = harness.service()

        await chat.handle_user_message(harness.group.id, "大家好", harness.responder({}))

        assert [call[0] for call in harness.calls] == ["coder"]


class TestHandoff:
    @pytest.mark.asyncio
    async def test_bot_reply_can_mention_another_bot(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        chat = harness.service()
        execute = harness.responder(
            {
                "watch": "行情在这：@coder 请整理成日报",
                "coder": "日报已生成",
            }
        )

        appended = await chat.handle_user_message(harness.group.id, "@watch 查行情", execute)

        assert [call[0] for call in harness.calls] == ["watch", "coder"]
        coder_context = harness.calls[1][1]
        assert any("@watch 查行情" in text for text in coder_context)
        assert any("行情在这" in text for text in coder_context)
        assert [m.author_type for m in appended] == ["user", "bot", "bot"]

    @pytest.mark.asyncio
    async def test_hop_limit_stops_the_chain(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        chat = harness.service(max_hops=1)
        execute = harness.responder(
            {
                "watch": "@coder 整理",
                "coder": "@watch 再看一眼",
            }
        )

        appended = await chat.handle_user_message(harness.group.id, "@watch 查", execute)

        assert [call[0] for call in harness.calls] == ["watch", "coder"]
        assert any("跳上限" in message.text for message in appended)

    @pytest.mark.asyncio
    async def test_bot_does_not_trigger_itself(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        chat = harness.service()
        execute = harness.responder({"watch": "@watch 我自己来"})

        appended = await chat.handle_user_message(harness.group.id, "@watch 查", execute)

        assert [call[0] for call in harness.calls] == ["watch"]
        assert len(appended) == 2

    @pytest.mark.asyncio
    async def test_bot_failure_is_reported(self, tmp_path: Path) -> None:
        harness = Harness(tmp_path)
        chat = harness.service()

        async def broken(*_args) -> str:
            raise RuntimeError("boom")

        appended = await chat.handle_user_message(harness.group.id, "@watch 查", broken)

        assert any("执行失败" in message.text for message in appended)
