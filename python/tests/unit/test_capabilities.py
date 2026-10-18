"""Unit tests for per-bot capability switches."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.capabilities import (
    CapabilityRepository,
    capability_id,
    describe,
    split_capability,
)


@pytest.fixture
def env(tmp_path: Path) -> tuple[CapabilityRepository, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return CapabilityRepository(db), bot.id


def test_capability_ids_round_trip() -> None:
    assert capability_id("mcp", "github") == "mcp:github"
    assert split_capability("mcp:github") == ("mcp", "github")
    assert split_capability("plain") == ("", "plain")


class TestCapabilityRepository:
    def test_default_is_enabled(self, env: tuple[CapabilityRepository, str]) -> None:
        repo, bot_id = env

        # MCP servers were globally available before this table existed; defaulting
        # to "off" would silently strip tools from every existing bot.
        assert repo.is_enabled(bot_id, "mcp:github") is True
        assert repo.overrides(bot_id) == {}

    def test_disabling_stores_an_override(self, env: tuple[CapabilityRepository, str]) -> None:
        repo, bot_id = env

        repo.set_enabled(bot_id, "mcp:github", False)

        assert repo.is_enabled(bot_id, "mcp:github") is False
        assert repo.overrides(bot_id) == {"mcp:github": False}

    def test_re_enabling_drops_the_row(self, env: tuple[CapabilityRepository, str]) -> None:
        repo, bot_id = env
        repo.set_enabled(bot_id, "mcp:github", False)

        repo.set_enabled(bot_id, "mcp:github", True)

        # Dropping the row keeps "default" meaning default.
        assert repo.overrides(bot_id) == {}
        assert repo.is_enabled(bot_id, "mcp:github") is True

    def test_overrides_are_per_bot(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        bots = BotRepository(db)
        first = bots.create("One")
        second = bots.create("Two")
        repo = CapabilityRepository(db)

        repo.set_enabled(first.id, "mcp:github", False)

        assert repo.is_enabled(first.id, "mcp:github") is False
        assert repo.is_enabled(second.id, "mcp:github") is True

    def test_disabled_mcp_servers_lists_only_mcp(self, env: tuple[CapabilityRepository, str]) -> None:
        repo, bot_id = env
        repo.set_enabled(bot_id, "mcp:github", False)
        repo.set_enabled(bot_id, "skill:deploy", False)

        assert repo.disabled_mcp_servers(bot_id) == {"github"}

    def test_rejects_empty_arguments(self, env: tuple[CapabilityRepository, str]) -> None:
        repo, bot_id = env

        with pytest.raises(ValueError, match="botId"):
            repo.set_enabled("", "mcp:github", False)
        with pytest.raises(ValueError, match="capability"):
            repo.set_enabled(bot_id, "", False)


class TestDescribe:
    def test_merges_connectors_with_switches(self, env: tuple[CapabilityRepository, str]) -> None:
        repo, bot_id = env
        repo.set_enabled(bot_id, "mcp:github", False)

        items = describe(
            bot_id,
            connectors=[
                {"name": "github", "label": "GitHub", "description": "issues"},
                {"name": "fs", "label": "Files"},
                {"label": "no name"},
            ],
            repo=repo,
        )

        assert [item["id"] for item in items] == ["mcp:github", "mcp:fs"]
        assert items[0]["enabled"] is False
        assert items[1]["enabled"] is True
        assert items[0]["kind"] == "mcp"
        assert items[0]["label"] == "GitHub"
        # A connector without a label falls back to its name; without a name it is skipped.
        assert items[1]["label"] == "Files"
