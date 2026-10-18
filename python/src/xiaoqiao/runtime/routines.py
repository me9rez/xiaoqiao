"""Routine definitions: scheduled prompts owned by a bot.

A routine only stores *what* to run and *when*; the scheduler decides when to
fire it and the gateway decides where the result goes.
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
class Routine:
    id: str
    bot_id: str
    name: str
    schedule: dict[str, Any]
    prompt: str
    target_group_id: str | None
    target_channel_id: str | None
    enabled: bool
    next_run_at: str | None
    last_run_at: str | None
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except TypeError, ValueError:
        return {}


def _row_to_routine(row: sqlite3.Row) -> Routine:
    return Routine(
        id=row["id"],
        bot_id=row["bot_id"],
        name=row["name"],
        schedule=_loads(row["schedule_json"]),
        prompt=row["prompt"],
        target_group_id=row["target_group_id"],
        target_channel_id=row["target_channel_id"],
        enabled=bool(row["enabled"]),
        next_run_at=row["next_run_at"],
        last_run_at=row["last_run_at"],
        created_at=row["created_at"],
    )


def routine_to_dict(routine: Routine) -> dict[str, Any]:
    return {
        "id": routine.id,
        "botId": routine.bot_id,
        "name": routine.name,
        "schedule": routine.schedule,
        "prompt": routine.prompt,
        "targetGroupId": routine.target_group_id,
        "targetChannelId": routine.target_channel_id,
        "enabled": routine.enabled,
        "nextRunAt": routine.next_run_at,
        "lastRunAt": routine.last_run_at,
        "createdAt": routine.created_at,
    }


class RoutineRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def set_steps(self, routine_id: str, steps: list[dict[str, Any]]) -> None:
        """Store the reviewed step list for a routine."""
        with self._connect() as conn:
            conn.execute("DELETE FROM routine_steps WHERE routine_id = ?", (routine_id,))
            if steps:
                conn.executemany(
                    "INSERT INTO routine_steps (routine_id, seq, tool, args_summary) VALUES (?, ?, ?, ?)",
                    [
                        (routine_id, index, item.get("tool", ""), item.get("argsSummary", ""))
                        for index, item in enumerate(steps)
                    ],
                )

    def steps(self, routine_id: str) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tool, args_summary FROM routine_steps WHERE routine_id = ? ORDER BY seq",
                (routine_id,),
            ).fetchall()
        return [{"tool": row["tool"], "argsSummary": row["args_summary"] or ""} for row in rows]

    def prompt_with_steps(self, routine: Routine) -> str:
        """Return the routine prompt with the recorded steps appended."""
        steps = self.steps(routine.id)
        if not steps:
            return routine.prompt
        lines = [routine.prompt.rstrip(), "", "上次的做法（按这个顺序，情况变了先说明再调整）："]
        for index, step in enumerate(steps, start=1):
            args = f"（{step['argsSummary']}）" if step["argsSummary"] else ""
            lines.append(f"{index}. {step['tool']}{args}")
        return "\n".join(lines)

    def get(self, routine_id: str) -> Routine | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM routines WHERE id = ?", (routine_id,)).fetchone()
        return _row_to_routine(row) if row else None

    def list(self, *, bot_id: str | None = None) -> list[Routine]:
        query = "SELECT * FROM routines"
        values: list[Any] = []
        if bot_id is not None:
            query += " WHERE bot_id = ?"
            values.append(bot_id)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_routine(row) for row in rows]

    def create(
        self,
        bot_id: str,
        name: str,
        schedule: dict[str, Any],
        prompt: str,
        *,
        target_group_id: str | None = None,
        target_channel_id: str | None = None,
        enabled: bool = True,
        next_run_at: str | None = None,
    ) -> Routine:
        routine_id = f"rt_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO routines (id, bot_id, name, schedule_json, prompt, target_group_id, "
                "target_channel_id, enabled, next_run_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    routine_id,
                    bot_id,
                    name.strip(),
                    json.dumps(schedule, ensure_ascii=False),
                    prompt,
                    target_group_id,
                    target_channel_id,
                    1 if enabled else 0,
                    next_run_at,
                    _now(),
                ),
            )
            row = conn.execute("SELECT * FROM routines WHERE id = ?", (routine_id,)).fetchone()
        assert row is not None
        return _row_to_routine(row)

    def update(self, routine_id: str, **fields: Any) -> Routine | None:
        columns = {
            "name": "name",
            "prompt": "prompt",
            "target_group_id": "target_group_id",
            "target_channel_id": "target_channel_id",
            "next_run_at": "next_run_at",
            "last_run_at": "last_run_at",
            "enabled": "enabled",
        }
        updates: list[str] = []
        values: list[Any] = []
        for key, column in columns.items():
            if key in fields:
                value = fields[key]
                if key == "enabled":
                    value = 1 if value else 0
                updates.append(f"{column} = ?")
                values.append(value)
        if "schedule" in fields:
            updates.append("schedule_json = ?")
            values.append(json.dumps(fields["schedule"], ensure_ascii=False))
        if not updates:
            return self.get(routine_id)
        values.append(routine_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE routines SET {', '.join(updates)} WHERE id = ?", values)
            row = conn.execute("SELECT * FROM routines WHERE id = ?", (routine_id,)).fetchone()
        return _row_to_routine(row) if row else None

    def toggle(self, routine_id: str, enabled: bool) -> Routine | None:
        return self.update(routine_id, enabled=enabled)

    def delete(self, routine_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
        return cursor.rowcount > 0

    def due(self, now_iso: str) -> list[Routine]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM routines WHERE enabled = 1 AND next_run_at IS NOT NULL "
                "AND next_run_at <= ? ORDER BY next_run_at ASC",
                (now_iso,),
            ).fetchall()
        return [_row_to_routine(row) for row in rows]

    def record_fire(self, routine_id: str, scheduled_at: str, run_id: str) -> bool:
        """Record one fire; returns False when this scheduled time already fired."""
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO routine_fires (routine_id, scheduled_at, run_id) VALUES (?, ?, ?)",
                    (routine_id, scheduled_at, run_id),
                )
            except sqlite3.IntegrityError:
                return False
        return True
