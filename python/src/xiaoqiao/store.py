"""SQLite storage for 小巧.

The database lives at ``~/.xiaoqiao/agent.db`` (WAL mode).  Everything the
runtime needs to survive a restart is persisted here: bots, groups, sessions,
runs, approvals, routines, memory, artifacts and usage.

JSONL session files remain supported as an import/export format only.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from xiaoqiao.paths import config_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bots (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  slug          TEXT UNIQUE NOT NULL,
  emoji         TEXT NOT NULL DEFAULT '🤖',
  persona_md    TEXT NOT NULL DEFAULT '',
  model         TEXT NOT NULL DEFAULT '',
  tools_json    TEXT NOT NULL DEFAULT '[]',
  workspace     TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  default_bot_id  TEXT REFERENCES bots(id) ON DELETE SET NULL,
  settings_json   TEXT NOT NULL DEFAULT '{}',
  archived        INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
  group_id    TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  member_type TEXT NOT NULL CHECK (member_type IN ('user','bot')),
  member_id   TEXT NOT NULL,
  joined_at   TEXT NOT NULL,
  PRIMARY KEY (group_id, member_type, member_id)
);

CREATE TABLE IF NOT EXISTS channels (
  id            TEXT PRIMARY KEY,
  bot_id        TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,
  config_json   TEXT NOT NULL DEFAULT '{}',
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_threads (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  channel_id         TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  external_thread_id TEXT NOT NULL,
  group_id           TEXT REFERENCES groups(id) ON DELETE SET NULL,
  session_id         TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  created_at         TEXT NOT NULL,
  UNIQUE (channel_id, external_thread_id)
);

CREATE TABLE IF NOT EXISTS sessions (
  id                TEXT PRIMARY KEY,
  bot_id            TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  group_id          TEXT REFERENCES groups(id) ON DELETE CASCADE,
  external_user_id  TEXT NOT NULL DEFAULT 'owner',
  title             TEXT NOT NULL DEFAULT '',
  model             TEXT NOT NULL DEFAULT '',
  workspace         TEXT NOT NULL DEFAULT '',
  status            TEXT NOT NULL DEFAULT 'idle',
  last_seen_seq     INTEGER NOT NULL DEFAULT 0,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  UNIQUE (bot_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_bot ON sessions(bot_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  role          TEXT NOT NULL,
  payload_json  TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  PRIMARY KEY (session_id, seq)
);

CREATE TABLE IF NOT EXISTS group_messages (
  id            TEXT PRIMARY KEY,
  group_id      TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  author_type   TEXT NOT NULL CHECK (author_type IN ('user','bot','system')),
  author_id     TEXT NOT NULL,
  content_json  TEXT NOT NULL,
  mentions_json TEXT NOT NULL DEFAULT '[]',
  reply_to      TEXT,
  run_id        TEXT,
  created_at    TEXT NOT NULL,
  UNIQUE (group_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_group_messages ON group_messages(group_id, created_at);

CREATE TABLE IF NOT EXISTS runs (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  session_id         TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  group_id           TEXT REFERENCES groups(id) ON DELETE SET NULL,
  trigger            TEXT NOT NULL,
  reply_to_message   TEXT,
  parent_run_id      TEXT,
  hop                INTEGER NOT NULL DEFAULT 0,
  status             TEXT NOT NULL,
  error              TEXT,
  started_at         TEXT,
  ended_at           TEXT,
  created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_bot ON runs(bot_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_group ON runs(group_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

CREATE TABLE IF NOT EXISTS routines (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  name               TEXT NOT NULL,
  schedule_json      TEXT NOT NULL,
  prompt             TEXT NOT NULL,
  target_group_id    TEXT REFERENCES groups(id) ON DELETE SET NULL,
  target_channel_id  TEXT REFERENCES channels(id) ON DELETE SET NULL,
  enabled            INTEGER NOT NULL DEFAULT 1,
  next_run_at        TEXT,
  last_run_at        TEXT,
  created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_routines_due ON routines(enabled, next_run_at);

CREATE TABLE IF NOT EXISTS routine_fires (
  routine_id    TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
  scheduled_at  TEXT NOT NULL,
  run_id        TEXT NOT NULL,
  PRIMARY KEY (routine_id, scheduled_at)
);

CREATE TABLE IF NOT EXISTS pending_approvals (
  id          TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  call_id     TEXT NOT NULL,
  bot_id      TEXT NOT NULL,
  group_id    TEXT,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,
  channel_id  TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_pending ON pending_approvals(status, expires_at);

CREATE TABLE IF NOT EXISTS memory_facts (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  user_id     TEXT NOT NULL DEFAULT 'owner',
  key         TEXT NOT NULL,
  value       TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'user',
  confidence  REAL NOT NULL DEFAULT 1.0,
  updated_at  TEXT NOT NULL,
  UNIQUE (bot_id, user_id, key)
);

CREATE TABLE IF NOT EXISTS memory_notes (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  user_id     TEXT NOT NULL DEFAULT 'owner',
  session_id  TEXT,
  text        TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_notes_fts USING fts5(
  text, content='memory_notes', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS memory_notes_ai AFTER INSERT ON memory_notes BEGIN
  INSERT INTO memory_notes_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memory_notes_ad AFTER DELETE ON memory_notes BEGIN
  INSERT INTO memory_notes_fts(memory_notes_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS memory_notes_au AFTER UPDATE ON memory_notes BEGIN
  INSERT INTO memory_notes_fts(memory_notes_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
  INSERT INTO memory_notes_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS artifacts (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  run_id      TEXT REFERENCES runs(id) ON DELETE SET NULL,
  path        TEXT NOT NULL,
  mime        TEXT,
  size        INTEGER,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
  id            TEXT PRIMARY KEY,
  run_id        TEXT REFERENCES runs(id) ON DELETE SET NULL,
  bot_id        TEXT NOT NULL,
  model         TEXT NOT NULL,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd      REAL NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);
"""


def db_path() -> Path:
    """Return the default database path."""
    return config_dir() / "agent.db"


@contextmanager
def connect(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with the pragmas the runtime relies on."""
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: str | Path | None = None) -> None:
    """Create the schema if needed and record the current version."""
    with connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        row = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        current = row["version"] if row and row["version"] is not None else 0
        if current < SCHEMA_VERSION:
            conn.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                (SCHEMA_VERSION,),
            )
            logger.info("Applied schema version %s (was %s)", SCHEMA_VERSION, current)
