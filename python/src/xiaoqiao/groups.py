"""Group chats: a human plus several bots in one shared thread.

Groups own membership and routing settings only.  Each bot still gets its own
session inside the group (see ``runtime/sessions.py``); the group is where the
messages and the @ routing live.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "autoReply": False,
    "maxHops": 3,
    "maxBotsPerTurn": 3,
}


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    default_bot_id: str | None
    settings: dict[str, Any] = field(default_factory=dict)
    archived: bool = False
    created_at: str = ""
    updated_at: str = ""
    bot_ids: tuple[str, ...] = ()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except TypeError, ValueError:
        return fallback


class GroupRepository:
    """CRUD and membership for groups."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def _bot_ids(self, conn: sqlite3.Connection, group_id: str) -> tuple[str, ...]:
        rows = conn.execute(
            "SELECT member_id FROM group_members WHERE group_id = ? AND member_type = 'bot' "
            "ORDER BY joined_at ASC, rowid ASC",
            (group_id,),
        ).fetchall()
        return tuple(row["member_id"] for row in rows)

    def _row_to_group(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Group:
        settings = dict(DEFAULT_SETTINGS)
        settings.update(_loads(row["settings_json"], {}))
        return Group(
            id=row["id"],
            name=row["name"],
            default_bot_id=row["default_bot_id"],
            settings=settings,
            archived=bool(row["archived"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            bot_ids=self._bot_ids(conn, row["id"]),
        )

    def list(self, *, include_archived: bool = False) -> list[Group]:
        query = "SELECT * FROM groups"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
            return [self._row_to_group(conn, row) for row in rows]

    def get(self, group_id: str) -> Group | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            return self._row_to_group(conn, row) if row else None

    def _assert_bots_exist(self, conn: sqlite3.Connection, bot_ids: list[str]) -> None:
        if not bot_ids:
            raise ValueError("group needs at least one bot")
        placeholders = ",".join("?" for _ in bot_ids)
        rows = conn.execute(f"SELECT id FROM bots WHERE id IN ({placeholders})", bot_ids).fetchall()
        found = {row["id"] for row in rows}
        missing = [bot_id for bot_id in bot_ids if bot_id not in found]
        if missing:
            raise ValueError(f"unknown bot(s): {', '.join(missing)}")

    def create(
        self,
        name: str,
        bot_ids: list[str],
        *,
        default_bot_id: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Group:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("group name must not be empty")
        if not bot_ids:
            raise ValueError("group needs at least one bot")
        unique_bots = list(dict.fromkeys(bot_ids))
        default = default_bot_id or unique_bots[0]
        if default not in unique_bots:
            raise ValueError("default bot must be a member of the group")
        merged = dict(DEFAULT_SETTINGS)
        merged.update(settings or {})
        group_id = f"grp_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._connect() as conn:
            self._assert_bots_exist(conn, unique_bots)
            conn.execute(
                "INSERT INTO groups (id, name, default_bot_id, settings_json, archived, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 0, ?, ?)",
                (group_id, cleaned, default, json.dumps(merged, ensure_ascii=False), now, now),
            )
            conn.execute(
                "INSERT INTO group_members (group_id, member_type, member_id, joined_at) "
                "VALUES (?, 'user', 'owner', ?)",
                (group_id, now),
            )
            for bot_id in unique_bots:
                conn.execute(
                    "INSERT INTO group_members (group_id, member_type, member_id, joined_at) VALUES (?, 'bot', ?, ?)",
                    (group_id, bot_id, now),
                )
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            assert row is not None
            return self._row_to_group(conn, row)

    def update(self, group_id: str, **changes: Any) -> Group | None:
        updates: list[str] = []
        values: list[Any] = []
        if "name" in changes:
            name = str(changes["name"]).strip()
            if not name:
                raise ValueError("group name must not be empty")
            updates.append("name = ?")
            values.append(name)
        if "defaultBotId" in changes or "default_bot_id" in changes:
            default = changes.get("defaultBotId", changes.get("default_bot_id"))
            if default is not None:
                with self._connect() as conn:
                    if default not in self._bot_ids(conn, group_id):
                        raise ValueError("default bot must be a member of the group")
            updates.append("default_bot_id = ?")
            values.append(default)
        if "settings" in changes:
            updates.append("settings_json = ?")
            values.append(json.dumps(dict(changes["settings"] or {}), ensure_ascii=False))
        if "archived" in changes:
            updates.append("archived = ?")
            values.append(1 if changes["archived"] else 0)
        if not updates:
            return self.get(group_id)
        updates.append("updated_at = ?")
        values.append(_now())
        values.append(group_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE groups SET {', '.join(updates)} WHERE id = ?", values)
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            return self._row_to_group(conn, row) if row else None

    def add_bot(self, group_id: str, bot_id: str) -> Group | None:
        now = _now()
        with self._connect() as conn:
            self._assert_bots_exist(conn, [bot_id])
            conn.execute(
                "INSERT OR IGNORE INTO group_members (group_id, member_type, member_id, joined_at) "
                "VALUES (?, 'bot', ?, ?)",
                (group_id, bot_id, now),
            )
            conn.execute("UPDATE groups SET updated_at = ? WHERE id = ?", (now, group_id))
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            return self._row_to_group(conn, row) if row else None

    def remove_bot(self, group_id: str, bot_id: str) -> Group | None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM group_members WHERE group_id = ? AND member_type = 'bot' AND member_id = ?",
                (group_id, bot_id),
            )
            remaining = self._bot_ids(conn, group_id)
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            if row is None:
                return None
            default = row["default_bot_id"]
            if default == bot_id:
                new_default = remaining[0] if remaining else None
                conn.execute(
                    "UPDATE groups SET default_bot_id = ?, updated_at = ? WHERE id = ?",
                    (new_default, now, group_id),
                )
            else:
                conn.execute("UPDATE groups SET updated_at = ? WHERE id = ?", (now, group_id))
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            return self._row_to_group(conn, row) if row else None

    def delete(self, group_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        return cursor.rowcount > 0
