"""Unit tests for the shared group transcript."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.groups import GroupRepository
from xiaoqiao.runtime.group_messages import GroupMessageRepository, message_to_dict


@pytest.fixture
def env(tmp_path: Path) -> tuple[GroupMessageRepository, str]:
    db = tmp_path / "agent.db"
    bots = BotRepository(db)
    groups = GroupRepository(db)
    bot = bots.create("Coder")
    group = groups.create("Daily", [bot.id])
    return GroupMessageRepository(db), group.id


class TestAppend:
    def test_sequence_increments(self, env: tuple[GroupMessageRepository, str]) -> None:
        messages, group_id = env
        first = messages.append(group_id, author_type="user", author_id="owner", text="hi")
        second = messages.append(group_id, author_type="bot", author_id="bot_1", text="hello")

        assert (first.seq, second.seq) == (1, 2)
        assert messages.last_seq(group_id) == 2

    def test_round_trips_mentions_and_reply(self, env: tuple[GroupMessageRepository, str]) -> None:
        messages, group_id = env
        user = messages.append(group_id, author_type="user", author_id="owner", text="@coder hi")
        reply = messages.append(
            group_id,
            author_type="bot",
            author_id="bot_1",
            text="done",
            mentions=["bot_2"],
            reply_to=user.id,
        )

        assert reply.mentions == ("bot_2",)
        assert reply.reply_to == user.id
        assert message_to_dict(reply)["mentions"] == ["bot_2"]


class TestQueries:
    def test_since_uses_watermark(self, env: tuple[GroupMessageRepository, str]) -> None:
        messages, group_id = env
        messages.append(group_id, author_type="user", author_id="owner", text="one")
        messages.append(group_id, author_type="user", author_id="owner", text="two")
        messages.append(group_id, author_type="user", author_id="owner", text="three")

        assert [m.text for m in messages.since(group_id, 1)] == ["two", "three"]

    def test_list_pages_backwards(self, env: tuple[GroupMessageRepository, str]) -> None:
        messages, group_id = env
        for index in range(5):
            messages.append(group_id, author_type="user", author_id="owner", text=str(index))

        latest = messages.list(group_id, limit=2)
        older = messages.list(group_id, limit=2, before_seq=latest[0].seq)

        assert [m.text for m in latest] == ["3", "4"]
        assert [m.text for m in older] == ["1", "2"]
