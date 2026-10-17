"""Unit tests for the SQLite schema and connection pragmas."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from xiaoqiao import store


def _tables(db: Path) -> set[str]:
    with store.connect(db) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


class TestInitDb:
    def test_creates_all_tables(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        store.init_db(db)

        tables = _tables(db)
        expected = {
            "bots",
            "groups",
            "group_members",
            "group_messages",
            "sessions",
            "messages",
            "runs",
            "routines",
            "routine_fires",
            "pending_approvals",
            "memory_facts",
            "memory_notes",
            "artifacts",
            "usage_events",
            "channel_threads",
        }
        assert expected <= tables

    def test_records_schema_version(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        store.init_db(db)
        store.init_db(db)

        with store.connect(db) as conn:
            version = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
        assert version == store.SCHEMA_VERSION

    def test_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        store.init_db(db)
        first = _tables(db)
        store.init_db(db)
        assert _tables(db) == first

    def test_enables_wal(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        store.init_db(db)
        with store.connect(db) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


class TestForeignKeys:
    def test_session_requires_existing_bot(self, tmp_path: Path) -> None:
        db = tmp_path / "agent.db"
        store.init_db(db)
        with pytest.raises(sqlite3.IntegrityError), store.connect(db) as conn:
            conn.execute(
                "INSERT INTO sessions (id, bot_id, title, created_at, updated_at) "
                "VALUES ('s1', 'missing', '', 'now', 'now')"
            )
