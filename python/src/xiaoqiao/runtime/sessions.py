"""Session metadata: one conversation context per (bot, group/thread).

The framework ``AgentSession`` remains the authoritative conversation state;
this repository only stores the metadata the runtime and UI need (which bot,
which group, title, workspace, watermark).
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionRecord:
    id: str
    bot_id: str
    group_id: str | None
    title: str
    model: str
    workspace: str
    status: str
    last_seen_seq: int
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_session(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        bot_id=row["bot_id"],
        group_id=row["group_id"],
        title=row["title"],
        model=row["model"],
        workspace=row["workspace"],
        status=row["status"],
        last_seen_seq=row["last_seen_seq"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SessionRepository:
    """CRUD for session metadata, backed by SQLite."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def get(self, session_id: str) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _row_to_session(row) if row else None

    def get_or_create(
        self,
        bot_id: str,
        *,
        group_id: str | None = None,
        title: str = "",
        model: str = "",
        workspace: str = "",
    ) -> SessionRecord:
        """Return the bot's session for a group, or create a fresh one."""
        if group_id is not None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE bot_id = ? AND group_id = ?",
                    (bot_id, group_id),
                ).fetchone()
            if row is not None:
                return _row_to_session(row)
        return self.create(
            bot_id,
            group_id=group_id,
            title=title,
            model=model,
            workspace=workspace,
        )

    def create(
        self,
        bot_id: str,
        *,
        group_id: str | None = None,
        title: str = "",
        model: str = "",
        workspace: str = "",
    ) -> SessionRecord:
        session_id = f"ses_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, bot_id, group_id, title, model, workspace, status, "
                "last_seen_seq, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'idle', 0, ?, ?)",
                (session_id, bot_id, group_id, title, model, workspace, now, now),
            )
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        assert row is not None
        return _row_to_session(row)

    def list(self, *, bot_id: str | None = None, group_id: str | None = None, limit: int = 50) -> list[SessionRecord]:
        query = "SELECT * FROM sessions"
        clauses: list[str] = []
        values: list[Any] = []
        if bot_id is not None:
            clauses.append("bot_id = ?")
            values.append(bot_id)
        if group_id is not None:
            clauses.append("group_id = ?")
            values.append(group_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_session(row) for row in rows]

    def update(self, session_id: str, **fields: Any) -> SessionRecord | None:
        allowed = {"title", "model", "workspace", "status", "last_seen_seq"}
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"unsupported session field: {key}")
            updates.append(f"{key} = ?")
            values.append(value)
        if not updates:
            return self.get(session_id)
        updates.append("updated_at = ?")
        values.append(_now())
        values.append(session_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", values)
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _row_to_session(row) if row else None

    def touch(self, session_id: str, *, status: str | None = None) -> None:
        with self._connect() as conn:
            if status is None:
                conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at = ?, status = ? WHERE id = ?",
                    (_now(), status, session_id),
                )
