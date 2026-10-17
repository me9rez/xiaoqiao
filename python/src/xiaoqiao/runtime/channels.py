"""Channel configuration: which bot listens where.

A channel row only stores transport config (tokens, allowed chats); the
adapters in ``xiaoqiao.channels`` own the actual polling and sending.
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
class Channel:
    id: str
    bot_id: str
    kind: str
    config: dict[str, Any]
    enabled: bool
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_channel(row: sqlite3.Row) -> Channel:
    try:
        config = json.loads(row["config_json"] or "{}")
    except TypeError, ValueError:
        config = {}
    return Channel(
        id=row["id"],
        bot_id=row["bot_id"],
        kind=row["kind"],
        config=config if isinstance(config, dict) else {},
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


def channel_to_dict(channel: Channel, *, redact: bool = True) -> dict[str, Any]:
    config = dict(channel.config)
    if redact:
        for key in ("token", "apiKey", "secret"):
            if config.get(key):
                config[key] = "***"
    return {
        "id": channel.id,
        "botId": channel.bot_id,
        "kind": channel.kind,
        "config": config,
        "enabled": channel.enabled,
        "createdAt": channel.created_at,
    }


class ChannelRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def get(self, channel_id: str) -> Channel | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
        return _row_to_channel(row) if row else None

    def list(self, *, bot_id: str | None = None, enabled_only: bool = False) -> list[Channel]:
        query = "SELECT * FROM channels"
        clauses: list[str] = []
        values: list[Any] = []
        if bot_id is not None:
            clauses.append("bot_id = ?")
            values.append(bot_id)
        if enabled_only:
            clauses.append("enabled = 1")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_channel(row) for row in rows]

    def create(
        self,
        bot_id: str,
        kind: str,
        config: dict[str, Any],
        *,
        enabled: bool = True,
    ) -> Channel:
        channel_id = f"ch_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO channels (id, bot_id, kind, config_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    channel_id,
                    bot_id,
                    kind,
                    json.dumps(config, ensure_ascii=False),
                    1 if enabled else 0,
                    _now(),
                ),
            )
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
        assert row is not None
        return _row_to_channel(row)

    def update(self, channel_id: str, **fields: Any) -> Channel | None:
        updates: list[str] = []
        values: list[Any] = []
        if "config" in fields:
            existing = self.get(channel_id)
            merged = {**(existing.config if existing else {}), **(fields["config"] or {})}
            updates.append("config_json = ?")
            values.append(json.dumps(merged, ensure_ascii=False))
        if "enabled" in fields:
            updates.append("enabled = ?")
            values.append(1 if fields["enabled"] else 0)
        if not updates:
            return self.get(channel_id)
        values.append(channel_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE channels SET {', '.join(updates)} WHERE id = ?", values)
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
        return _row_to_channel(row) if row else None

    def delete(self, channel_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        return cursor.rowcount > 0
