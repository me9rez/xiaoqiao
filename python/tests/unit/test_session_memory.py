"""Unit tests for deterministic session digesting into memory notes."""

from __future__ import annotations

from pathlib import Path

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.memory import MemoryRepository
from xiaoqiao.runtime.session_memory import MAX_CHARS, format_note, summarize_session


def _message(role: str, text: str) -> dict:
    return {"role": role, "contents": [{"type": "text", "text": text}]}


class TestSummarize:
    def test_collects_user_asks(self) -> None:
        summary = summarize_session(
            [
                _message("user", "帮我整理日报"),
                _message("assistant", "好的"),
                _message("user", "再补一个行情"),
            ]
        )

        assert summary == "帮我整理日报；再补一个行情"

    def test_ignores_non_text_and_non_user(self) -> None:
        summary = summarize_session(
            [
                {"role": "user", "contents": [{"type": "function_call", "name": "x"}]},
                _message("assistant", "结果在这里"),
            ]
        )

        assert summary is None

    def test_deduplicates_consecutive_asks(self) -> None:
        summary = summarize_session([_message("user", "继续"), _message("user", "继续")])
        assert summary == "继续"

    def test_truncates_long_digest(self) -> None:
        summary = summarize_session([_message("user", "x" * 1000)])
        assert summary is not None
        assert len(summary) == MAX_CHARS
        assert summary.endswith("…")

    def test_keeps_only_recent_asks(self) -> None:
        messages = [_message("user", f"ask-{index}") for index in range(8)]
        summary = summarize_session(messages)
        assert summary is not None
        assert "ask-0" not in summary
        assert "ask-7" in summary

    def test_format_note_prefix(self) -> None:
        assert format_note("干了点事") == "会话摘要：干了点事"


class TestSessionNote:
    def test_rolling_note_per_session(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        bot = BotRepository(db).create("Coder")
        memory = MemoryRepository(db)

        memory.upsert_session_note(bot.id, "ses_1", format_note("第一轮"))
        updated = memory.upsert_session_note(bot.id, "ses_1", format_note("第二轮"))

        notes = [note for note in memory.recent_notes(bot.id) if note.session_id == "ses_1"]
        assert len(notes) == 1
        assert notes[0].id == updated.id
        assert notes[0].text == "会话摘要：第二轮"

    def test_separate_sessions_get_separate_notes(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        bot = BotRepository(db).create("Coder")
        memory = MemoryRepository(db)

        memory.upsert_session_note(bot.id, "ses_1", format_note("A"))
        memory.upsert_session_note(bot.id, "ses_2", format_note("B"))

        assert len(memory.recent_notes(bot.id)) == 2
