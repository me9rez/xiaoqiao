"""Unit tests for long-term memory: facts, notes, search and prompt block."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.memory import MemoryRepository
from xiaoqiao.system_prompt import BuildSystemPromptOptions, build_system_prompt


@pytest.fixture
def env(tmp_path: Path) -> tuple[MemoryRepository, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return MemoryRepository(db), bot.id


class TestFacts:
    def test_upsert_creates_and_updates(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        created = memory.upsert_fact(bot_id, "称呼", "叫他老王")
        updated = memory.upsert_fact(bot_id, "称呼", "叫他王工")

        assert created.id == updated.id
        assert updated.value == "叫他王工"
        assert [fact.value for fact in memory.list_facts(bot_id)] == ["叫他王工"]

    def test_rejects_empty_values(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        with pytest.raises(ValueError):
            memory.upsert_fact(bot_id, "k", "  ")
        with pytest.raises(ValueError):
            memory.upsert_fact(bot_id, "  ", "v")

    def test_delete(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        memory.upsert_fact(bot_id, "偏好", "中文")
        assert memory.delete_fact(bot_id, "偏好") is True
        assert memory.list_facts(bot_id) == []

    def test_scoped_per_bot(self, env: tuple[MemoryRepository, str], tmp_path: Path) -> None:
        memory, bot_id = env
        other = BotRepository(tmp_path / "agent.db").create("Other")
        memory.upsert_fact(bot_id, "k", "v")

        assert len(memory.list_facts(bot_id)) == 1
        assert memory.list_facts(other.id) == []


class TestNotes:
    def test_recent_notes(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        memory.add_note(bot_id, "上周决定用 SQLite")
        memory.add_note(bot_id, "用户偏好中文回复")

        assert memory.recent_notes(bot_id)[0].text == "用户偏好中文回复"

    def test_search_notes(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        memory.add_note(bot_id, "上周决定用 SQLite 存会话")
        memory.add_note(bot_id, "用户偏好中文回复")

        hits = memory.search_notes(bot_id, "SQLite")
        assert [note.text for note in hits] == ["上周决定用 SQLite 存会话"]

    def test_search_is_scoped_per_bot(self, env: tuple[MemoryRepository, str], tmp_path: Path) -> None:
        memory, bot_id = env
        other = BotRepository(tmp_path / "agent.db").create("Other")
        memory.add_note(other.id, "SQLite 是另一个 Bot 的记忆")

        assert memory.search_notes(bot_id, "SQLite") == []


class TestPromptBlock:
    def test_block_lists_facts(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        memory.upsert_fact(bot_id, "称呼", "叫他老王")

        block = memory.build_block(bot_id)

        assert "## 关于用户的记忆" in block
        assert "- 称呼: 叫他老王" in block

    def test_block_is_empty_without_memory(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        assert memory.build_block(bot_id) == ""

    def test_block_is_truncated(self, env: tuple[MemoryRepository, str]) -> None:
        memory, bot_id = env
        memory.upsert_fact(bot_id, "长", "x" * 500)

        block = memory.build_block(bot_id, max_chars=50)

        assert len(block) <= 50
        assert block.endswith("…")

    def test_prompt_includes_block(self) -> None:
        prompt = build_system_prompt(BuildSystemPromptOptions(memory_block="## 关于用户的记忆\n- 称呼: 老王"))
        assert "## 关于用户的记忆" in prompt

    def test_prompt_without_block(self) -> None:
        assert "## 关于用户的记忆" not in build_system_prompt(BuildSystemPromptOptions())
