"""Unit tests for bot CRUD and the default bot bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository, LastBotError, bot_to_dict


@pytest.fixture
def repo(tmp_path: Path) -> BotRepository:
    return BotRepository(tmp_path / "agent.db")


class TestBotCrud:
    def test_create_and_list(self, repo: BotRepository) -> None:
        bot = repo.create("Coder", emoji="🧑‍💻", persona="You code.", model="deepseek/deepseek-v4")
        bots = repo.list()

        assert [b.id for b in bots] == [bot.id]
        assert bot.name == "Coder"
        assert bot.emoji == "🧑‍💻"
        assert bot.persona == "You code."
        assert bot.model == "deepseek/deepseek-v4"

    def test_get_by_slug(self, repo: BotRepository) -> None:
        bot = repo.create("Watch Bot")
        assert repo.get_by_slug("watch-bot") == bot

    def test_slug_is_unique(self, repo: BotRepository) -> None:
        first = repo.create("Helper")
        second = repo.create("Helper")
        assert first.slug == "helper"
        assert second.slug == "helper-2"

    def test_validate_empty_name(self, repo: BotRepository) -> None:
        with pytest.raises(ValueError):
            repo.create("   ")

    def test_update_fields(self, repo: BotRepository) -> None:
        bot = repo.create("Coder")
        updated = repo.update(bot.id, name="Builder", persona="Ship it.", tools=["read_file"])

        assert updated is not None
        assert updated.name == "Builder"
        assert updated.persona == "Ship it."
        assert updated.tools == ("read_file",)
        assert updated.slug == bot.slug

    def test_update_unknown_bot(self, repo: BotRepository) -> None:
        assert repo.update("bot_missing", name="X") is None

    def test_tools_round_trip(self, repo: BotRepository) -> None:
        bot = repo.create("Coder", tools=["read_file", "run_command"])
        loaded = repo.get(bot.id)
        assert loaded is not None
        assert loaded.tools == ("read_file", "run_command")

    def test_delete(self, repo: BotRepository) -> None:
        first = repo.create("One")
        repo.create("Two")
        assert repo.delete(first.id) is True
        assert repo.get(first.id) is None

    def test_cannot_delete_last_bot(self, repo: BotRepository) -> None:
        bot = repo.create("Only")
        with pytest.raises(LastBotError):
            repo.delete(bot.id)


class TestEnsureDefault:
    def test_creates_once(self, repo: BotRepository) -> None:
        first = repo.ensure_default()
        second = repo.ensure_default()

        assert first.id == second.id
        assert len(repo.list()) == 1
        assert first.name == "Coder"

    def test_keeps_existing_bot(self, repo: BotRepository) -> None:
        existing = repo.create("Watch")
        assert repo.ensure_default().id == existing.id


def test_bot_to_dict(repo: BotRepository) -> None:
    bot = repo.create("Coder", tools=["read_file"])
    data = bot_to_dict(bot)
    assert data["name"] == "Coder"
    assert data["tools"] == ["read_file"]
    assert data["createdAt"]
