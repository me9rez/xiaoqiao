"""Unit tests for artifact indexing and workspace scanning."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xiaoqiao import store
from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.artifacts import ArtifactRepository


def _run(db: Path, bot_id: str, run_id: str) -> str:
    with store.connect(db) as conn:
        conn.execute(
            "INSERT INTO runs (id, bot_id, trigger, status, created_at) VALUES (?, ?, 'web', 'done', ?)",
            (run_id, bot_id, datetime.now(UTC).isoformat()),
        )
    return run_id


@pytest.fixture
def env(tmp_path: Path) -> tuple[ArtifactRepository, str, Path]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return ArtifactRepository(db), bot.id, db


class TestRecord:
    def test_records_and_lists(self, env: tuple[ArtifactRepository, str, Path]) -> None:
        artifacts, bot_id, db = env
        run_id = _run(db, bot_id, "run_1")
        artifact = artifacts.record(bot_id, "reports/daily.md", run_id=run_id, size=120)

        assert artifact.mime == "text/markdown"
        assert artifact.size == 120
        assert [item.id for item in artifacts.list(bot_id=bot_id)] == [artifact.id]
        assert [item.id for item in artifacts.list(run_id=run_id)] == [artifact.id]

    def test_same_path_is_deduplicated(self, env: tuple[ArtifactRepository, str, Path]) -> None:
        artifacts, bot_id, db = env
        first = artifacts.record(bot_id, "out.txt")
        second_run = _run(db, bot_id, "run_2")
        second = artifacts.record(bot_id, "out.txt", run_id=second_run)

        assert first.id == second.id
        assert len(artifacts.list(bot_id=bot_id)) == 1
        assert second.run_id == second_run

    def test_scoped_by_bot(self, env: tuple[ArtifactRepository, str, Path], tmp_path: Path) -> None:
        artifacts, bot_id, _ = env
        other = BotRepository(tmp_path / "agent.db").create("Other")
        artifacts.record(other.id, "x.txt")

        assert artifacts.list(bot_id=bot_id) == []


class TestScan:
    def test_indexes_only_recent_files(self, env: tuple[ArtifactRepository, str, Path], tmp_path: Path) -> None:
        artifacts, bot_id, _ = env
        workspace = tmp_path / "ws"
        workspace.mkdir()
        old_file = workspace / "old.txt"
        new_file = workspace / "new.md"
        old_file.write_text("old", encoding="utf-8")
        new_file.write_text("new", encoding="utf-8")

        old_time = (datetime.now(UTC) - timedelta(hours=2)).timestamp()
        os.utime(old_file, (old_time, old_time))
        since = datetime.now(UTC) - timedelta(minutes=5)

        found = artifacts.scan_workspace(bot_id, workspace, since=since)

        assert [item.path for item in found] == ["new.md"]
        assert found[0].mime == "text/markdown"

    def test_skips_ignored_directories(self, env: tuple[ArtifactRepository, str, Path], tmp_path: Path) -> None:
        artifacts, bot_id, _ = env
        workspace = tmp_path / "ws"
        (workspace / "node_modules").mkdir(parents=True)
        (workspace / "node_modules" / "dep.js").write_text("x", encoding="utf-8")
        (workspace / "keep.txt").write_text("x", encoding="utf-8")

        found = artifacts.scan_workspace(
            bot_id,
            workspace,
            since=datetime.now(UTC) - timedelta(minutes=5),
        )

        assert [item.path for item in found] == ["keep.txt"]

    def test_missing_workspace_is_empty(self, env: tuple[ArtifactRepository, str, Path], tmp_path: Path) -> None:
        artifacts, bot_id, _ = env
        assert artifacts.scan_workspace(bot_id, tmp_path / "nope", since=datetime.now(UTC)) == []
