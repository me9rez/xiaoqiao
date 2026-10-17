"""Unit tests for local state backups."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao import store
from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.backup import create_backup, verify_backup


@pytest.fixture
def live_state(tmp_path: Path) -> Path:
    source = tmp_path / "state"
    source.mkdir()
    BotRepository(source / "agent.db").create("Coder")
    (source / "settings.json").write_text('{"max_turns": 5}', encoding="utf-8")
    sessions = source / "sessions"
    sessions.mkdir()
    (sessions / "s1.jsonl").write_text("", encoding="utf-8")
    return source


class TestBackup:
    def test_copies_database_settings_and_sessions(self, live_state: Path, tmp_path: Path) -> None:
        created = create_backup(tmp_path / "backups", source=live_state)

        assert set(created) == {"database", "sessions", "settings.json"}
        assert Path(created["database"]).is_file()
        assert Path(created["settings.json"]).read_text(encoding="utf-8") == '{"max_turns": 5}'

    def test_backup_database_is_usable(self, live_state: Path, tmp_path: Path) -> None:
        created = create_backup(tmp_path / "backups", source=live_state)
        database = Path(created["database"])

        assert verify_backup(database) is True

        with store.connect(database) as conn:
            bots = conn.execute("SELECT name FROM bots").fetchall()
        assert [row["name"] for row in bots] == ["Coder"]

    def test_missing_source_yields_empty_backup(self, tmp_path: Path) -> None:
        created = create_backup(tmp_path / "backups", source=tmp_path / "nope")
        assert created == {}

    def test_verify_rejects_garbage(self, tmp_path: Path) -> None:
        fake = tmp_path / "agent.db"
        fake.write_text("not a database", encoding="utf-8")
        assert verify_backup(fake) is False
