"""Shared transcript for group chats.

Unlike ``messages`` (a per-session projection for direct chats), these rows are
the single source of truth for a group: author, mentions and reply links live
here, and every bot reads from it with its own watermark.
"""

from __future__ import annotations

import json
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
class GroupMessage:
    id: str
    group_id: str
    seq: int
    author_type: str  # user | bot | system
    author_id: str
    text: str
    mentions: tuple[str, ...]
    reply_to: str | None
    run_id: str | None
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_message(row: sqlite3.Row) -> GroupMessage:
    try:
        content = json.loads(row["content_json"] or "{}")
    except TypeError, ValueError:
        content = {}
    try:
        mentions = tuple(json.loads(row["mentions_json"] or "[]"))
    except TypeError, ValueError:
        mentions = ()
    return GroupMessage(
        id=row["id"],
        group_id=row["group_id"],
        seq=row["seq"],
        author_type=row["author_type"],
        author_id=row["author_id"],
        text=content.get("text", ""),
        mentions=mentions,
        reply_to=row["reply_to"],
        run_id=row["run_id"],
        created_at=row["created_at"],
    )


def message_to_dict(message: GroupMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "groupId": message.group_id,
        "seq": message.seq,
        "authorType": message.author_type,
        "authorId": message.author_id,
        "text": message.text,
        "mentions": list(message.mentions),
        "replyTo": message.reply_to,
        "runId": message.run_id,
        "createdAt": message.created_at,
    }


class GroupMessageRepository:
    """Append-only store for group messages."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def append(
        self,
        group_id: str,
        *,
        author_type: str,
        author_id: str,
        text: str,
        mentions: list[str] | tuple[str, ...] = (),
        reply_to: str | None = None,
        run_id: str | None = None,
    ) -> GroupMessage:
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM group_messages WHERE group_id = ?",
                (group_id,),
            ).fetchone()["next"]
            conn.execute(
                "INSERT INTO group_messages (id, group_id, seq, author_type, author_id, "
                "content_json, mentions_json, reply_to, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message_id,
                    group_id,
                    seq,
                    author_type,
                    author_id,
                    json.dumps({"text": text}, ensure_ascii=False),
                    json.dumps(list(mentions), ensure_ascii=False),
                    reply_to,
                    run_id,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM group_messages WHERE id = ?", (message_id,)).fetchone()
        assert row is not None
        return _row_to_message(row)

    def since(self, group_id: str, seq: int, *, limit: int = 200) -> list[GroupMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM group_messages WHERE group_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                (group_id, seq, limit),
            ).fetchall()
        return [_row_to_message(row) for row in rows]

    def list(self, group_id: str, *, limit: int = 100, before_seq: int | None = None) -> list[GroupMessage]:
        """Newest-last page; ``before_seq`` pages backwards."""
        query = "SELECT * FROM group_messages WHERE group_id = ?"
        values: list[Any] = [group_id]
        if before_seq is not None:
            query += " AND seq < ?"
            values.append(before_seq)
        query += " ORDER BY seq DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_message(row) for row in reversed(rows)]

    def last_seq(self, group_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS seq FROM group_messages WHERE group_id = ?",
                (group_id,),
            ).fetchone()
        return int(row["seq"])
