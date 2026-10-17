"""Long-term memory: user facts plus searchable session notes.

Facts are short key/value statements injected into the prompt; notes are freer
records searched with FTS5 when the current message looks related.  Everything
is scoped to (bot, user) so different assistants never share a personality's
memories by accident.
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

OWNER = "owner"
DEFAULT_BLOCK_CHARS = 2000


@dataclass(frozen=True)
class Fact:
    id: str
    bot_id: str
    user_id: str
    key: str
    value: str
    source: str
    confidence: float
    updated_at: str


@dataclass(frozen=True)
class Note:
    id: str
    bot_id: str
    user_id: str
    session_id: str | None
    text: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        id=row["id"],
        bot_id=row["bot_id"],
        user_id=row["user_id"],
        key=row["key"],
        value=row["value"],
        source=row["source"],
        confidence=row["confidence"],
        updated_at=row["updated_at"],
    )


def _row_to_note(row: sqlite3.Row) -> Note:
    return Note(
        id=row["id"],
        bot_id=row["bot_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        text=row["text"],
        created_at=row["created_at"],
    )


def fact_to_dict(fact: Fact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "botId": fact.bot_id,
        "key": fact.key,
        "value": fact.value,
        "source": fact.source,
        "confidence": fact.confidence,
        "updatedAt": fact.updated_at,
    }


def note_to_dict(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "botId": note.bot_id,
        "sessionId": note.session_id,
        "text": note.text,
        "createdAt": note.created_at,
    }


class MemoryRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    # ── facts ────────────────────────────────────────────────────

    def upsert_fact(
        self,
        bot_id: str,
        key: str,
        value: str,
        *,
        user_id: str = OWNER,
        source: str = "user",
        confidence: float = 1.0,
    ) -> Fact:
        cleaned_key = key.strip()
        cleaned_value = value.strip()
        if not cleaned_key:
            raise ValueError("memory key must not be empty")
        if not cleaned_value:
            raise ValueError("memory value must not be empty")
        now = _now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM memory_facts WHERE bot_id = ? AND user_id = ? AND key = ?",
                (bot_id, user_id, cleaned_key),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE memory_facts SET value = ?, source = ?, confidence = ?, updated_at = ? WHERE id = ?",
                    (cleaned_value, source, confidence, now, existing["id"]),
                )
                fact_id = existing["id"]
            else:
                fact_id = f"fact_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO memory_facts (id, bot_id, user_id, key, value, source, confidence, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (fact_id, bot_id, user_id, cleaned_key, cleaned_value, source, confidence, now),
                )
            row = conn.execute("SELECT * FROM memory_facts WHERE id = ?", (fact_id,)).fetchone()
        assert row is not None
        return _row_to_fact(row)

    def list_facts(self, bot_id: str, *, user_id: str = OWNER) -> list[Fact]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_facts WHERE bot_id = ? AND user_id = ? ORDER BY updated_at DESC",
                (bot_id, user_id),
            ).fetchall()
        return [_row_to_fact(row) for row in rows]

    def delete_fact(self, bot_id: str, key: str, *, user_id: str = OWNER) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM memory_facts WHERE bot_id = ? AND user_id = ? AND key = ?",
                (bot_id, user_id, key),
            )
        return cursor.rowcount > 0

    # ── notes ────────────────────────────────────────────────────

    def add_note(
        self,
        bot_id: str,
        text: str,
        *,
        session_id: str | None = None,
        user_id: str = OWNER,
    ) -> Note:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("memory note must not be empty")
        note_id = f"note_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory_notes (id, bot_id, user_id, session_id, text, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (note_id, bot_id, user_id, session_id, cleaned, _now()),
            )
            row = conn.execute("SELECT * FROM memory_notes WHERE id = ?", (note_id,)).fetchone()
        assert row is not None
        return _row_to_note(row)

    def upsert_session_note(
        self,
        bot_id: str,
        session_id: str,
        text: str,
        *,
        user_id: str = OWNER,
    ) -> Note:
        """Keep exactly one rolling note per session."""
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("memory note must not be empty")
        now = _now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM memory_notes WHERE bot_id = ? AND user_id = ? AND session_id = ?",
                (bot_id, user_id, session_id),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE memory_notes SET text = ?, created_at = ? WHERE id = ?",
                    (cleaned, now, existing["id"]),
                )
                note_id = existing["id"]
            else:
                note_id = f"note_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO memory_notes (id, bot_id, user_id, session_id, text, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (note_id, bot_id, user_id, session_id, cleaned, now),
                )
            row = conn.execute("SELECT * FROM memory_notes WHERE id = ?", (note_id,)).fetchone()
        assert row is not None
        return _row_to_note(row)

    def recent_notes(self, bot_id: str, *, limit: int = 5) -> list[Note]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_notes WHERE bot_id = ? ORDER BY created_at DESC LIMIT ?",
                (bot_id, limit),
            ).fetchall()
        return [_row_to_note(row) for row in rows]

    def search_notes(self, bot_id: str, query: str, *, limit: int = 5) -> list[Note]:
        tokens = [token for token in query.replace('"', " ").split() if token]
        if not tokens:
            return []
        expression = " OR ".join(f'"{token}"' for token in tokens)
        with self._connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT n.* FROM memory_notes_fts f JOIN memory_notes n ON n.rowid = f.rowid "
                    "WHERE memory_notes_fts MATCH ? AND n.bot_id = ? "
                    "ORDER BY rank LIMIT ?",
                    (expression, bot_id, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                logger.warning("FTS query failed for %r", query)
                return []
        return [_row_to_note(row) for row in rows]

    # ── prompt block ─────────────────────────────────────────────

    def build_block(
        self,
        bot_id: str,
        *,
        user_id: str = OWNER,
        max_chars: int = DEFAULT_BLOCK_CHARS,
        query: str = "",
    ) -> str:
        """Render facts and (optionally) related notes for the system prompt."""
        facts = self.list_facts(bot_id, user_id=user_id)
        notes = self.search_notes(bot_id, query) if query.strip() else self.recent_notes(bot_id)
        if not facts and not notes:
            return ""

        lines = ["## 关于用户的记忆"]
        for fact in facts:
            lines.append(f"- {fact.key}: {fact.value}")
        if notes:
            lines.append("")
            lines.append("## 相关记录")
            for note in notes:
                lines.append(f"- {note.text}")
        block = "\n".join(lines)
        if len(block) > max_chars:
            block = block[: max_chars - 1].rstrip() + "…"
        return block
