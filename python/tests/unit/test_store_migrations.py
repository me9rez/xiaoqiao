"""Tests for the forward-only schema migrations in ``store.py``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from xiaoqiao import store


def _columns(db: Path, table: str) -> set[str]:
    with store.connect(db) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


@pytest.fixture
def v2_db(tmp_path: Path) -> Path:
    """A database shaped like the v2 release: bots table without the new columns."""
    db = tmp_path / "agent.db"
    with store.connect(db) as conn:
        conn.executescript(store.SCHEMA_SQL)
        # The v2 layout predates role/description, and the migration runner is what
        # upgrades it — so strip the columns a fresh CREATE would now include.
        conn.execute("DROP TABLE IF EXISTS bots")
        conn.execute(
            """
            CREATE TABLE bots (
              id           TEXT PRIMARY KEY,
              name         TEXT NOT NULL,
              slug         TEXT NOT NULL UNIQUE,
              emoji        TEXT NOT NULL DEFAULT '🤖',
              persona_md   TEXT NOT NULL DEFAULT '',
              model        TEXT NOT NULL DEFAULT '',
              tools_json   TEXT NOT NULL DEFAULT '[]',
              workspace    TEXT NOT NULL DEFAULT '',
              created_at   TEXT NOT NULL,
              updated_at   TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO bots (id, name, slug, created_at, updated_at) VALUES ('bot_1', 'Chief', 'chief', 'x', 'x')"
        )
        conn.execute("INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (2, datetime('now'))")
    return db


class TestMigrations:
    def test_v2_database_gains_the_bot_profile_columns(self, v2_db: Path) -> None:
        assert "role" not in _columns(v2_db, "bots")

        store.init_db(v2_db)

        columns = _columns(v2_db, "bots")
        assert {"role", "description"} <= columns
        with store.connect(v2_db) as conn:
            row = conn.execute("SELECT role, description FROM bots WHERE id = 'bot_1'").fetchone()
            version = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        # Existing rows get the empty default, never NULL.
        assert (row["role"], row["description"]) == ("", "")
        assert version["version"] == store.SCHEMA_VERSION

    def test_running_twice_is_idempotent(self, v2_db: Path) -> None:
        store.init_db(v2_db)
        store.init_db(v2_db)

        assert {"role", "description"} <= _columns(v2_db, "bots")

    def test_fresh_database_starts_at_the_current_version(self, tmp_path: Path) -> None:
        db = tmp_path / "fresh.db"

        store.init_db(db)

        with store.connect(db) as conn:
            version = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        assert version["version"] == store.SCHEMA_VERSION
        assert {"role", "description"} <= _columns(db, "bots")

    def test_a_hand_added_column_does_not_block_startup(self, v2_db: Path) -> None:
        store.init_db(v2_db)
        # Simulate "column added by hand, version never recorded".
        with store.connect(v2_db) as conn:
            conn.execute("DELETE FROM schema_migrations")

        store.init_db(v2_db)

        with store.connect(v2_db) as conn:
            version = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        assert version["version"] == store.SCHEMA_VERSION


def test_migration_versions_are_monotonic() -> None:
    versions = [version for version, _ in store.MIGRATIONS]
    assert versions == sorted(versions)
    assert all(version <= store.SCHEMA_VERSION for version in versions)
    assert not any(
        "sqlite" in statement.lower() and "pragma" in statement.lower() for _, statement in store.MIGRATIONS
    ), "migrations must be plain statements the runner can execute"


def test_database_file_is_reusable_after_migration(v2_db: Path) -> None:
    store.init_db(v2_db)
    with store.connect(v2_db) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM bots").fetchone()["n"] == 1
    with pytest.raises(sqlite3.OperationalError), store.connect(v2_db) as conn:
        conn.execute("SELECT definitely_missing_column FROM bots")
