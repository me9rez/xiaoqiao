"""Unit tests for channel configuration storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.channels import ChannelRepository, channel_to_dict


@pytest.fixture
def env(tmp_path: Path) -> tuple[ChannelRepository, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return ChannelRepository(db), bot.id


class TestChannelRepository:
    def test_create_and_list(self, env: tuple[ChannelRepository, str]) -> None:
        channels, bot_id = env
        channel = channels.create(bot_id, "telegram", {"token": "secret", "chat_id": "42"})

        assert channel.kind == "telegram"
        assert channel.config["chat_id"] == "42"
        assert [item.id for item in channels.list(bot_id=bot_id)] == [channel.id]

    def test_update_and_toggle(self, env: tuple[ChannelRepository, str]) -> None:
        channels, bot_id = env
        channel = channels.create(bot_id, "telegram", {"token": "old"})

        updated = channels.update(channel.id, config={"token": "new"}, enabled=False)

        assert updated is not None
        assert updated.config["token"] == "new"
        assert updated.enabled is False
        assert channels.list(enabled_only=True) == []

    def test_delete(self, env: tuple[ChannelRepository, str]) -> None:
        channels, bot_id = env
        channel = channels.create(bot_id, "telegram", {})

        assert channels.delete(channel.id) is True
        assert channels.get(channel.id) is None

    def test_redacts_secrets(self, env: tuple[ChannelRepository, str]) -> None:
        channels, bot_id = env
        channel = channels.create(bot_id, "telegram", {"token": "secret", "chat_id": "42"})

        payload = channel_to_dict(channel)

        assert payload["config"]["token"] == "***"
        assert payload["config"]["chat_id"] == "42"
