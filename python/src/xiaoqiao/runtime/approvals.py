"""Durable tool approvals.

Approvals are run-scoped and stored in SQLite so a routine or channel-triggered
run cannot be stranded when no browser is connected.  Only the human owner may
resolve one; bots never approve each other.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)

OWNER = "owner"


@dataclass(frozen=True)
class Approval:
    id: str
    run_id: str
    call_id: str
    bot_id: str
    group_id: str | None
    tool: str
    args: dict[str, Any]
    status: str
    created_at: str
    expires_at: str
    resolved_at: str | None
    resolved_by: str | None


def _now() -> datetime:
    return datetime.now(UTC)


def _row_to_approval(row: sqlite3.Row) -> Approval:
    try:
        args = json.loads(row["args_json"] or "{}")
    except TypeError, ValueError:
        args = {}
    return Approval(
        id=row["id"],
        run_id=row["run_id"],
        call_id=row["call_id"],
        bot_id=row["bot_id"],
        group_id=row["group_id"],
        tool=row["tool"],
        args=args,
        status=row["status"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
    )


def approval_to_dict(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "runId": approval.run_id,
        "callId": approval.call_id,
        "botId": approval.bot_id,
        "groupId": approval.group_id,
        "tool": approval.tool,
        "arguments": approval.args,
        "status": approval.status,
        "createdAt": approval.created_at,
        "expiresAt": approval.expires_at,
        "resolvedAt": approval.resolved_at,
        "resolvedBy": approval.resolved_by,
    }


class ApprovalBroker:
    """Create, list and resolve approvals; expiry is evaluated lazily."""

    def __init__(self, db_path: str | Path | None = None, *, ttl_seconds: int = 1800) -> None:
        self._path = db_path
        self._ttl = ttl_seconds
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def create_run(
        self,
        bot_id: str,
        *,
        group_id: str | None = None,
        trigger: str = "web",
    ) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, bot_id, session_id, group_id, trigger, hop, status, created_at) "
                "VALUES (?, ?, NULL, ?, ?, 0, 'waiting_approval', ?)",
                (run_id, bot_id, group_id, trigger, _now().isoformat()),
            )
        return run_id

    def create(
        self,
        run_id: str,
        call_id: str,
        bot_id: str,
        tool: str,
        args: dict[str, Any] | str,
        *,
        group_id: str | None = None,
        channel_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> Approval:
        approval_id = f"ap_{uuid.uuid4().hex[:12]}"
        created = _now()
        expires = created + timedelta(seconds=self._ttl if ttl_seconds is None else ttl_seconds)
        payload = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pending_approvals (id, run_id, call_id, bot_id, group_id, tool, args_json, "
                "channel_id, status, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    approval_id,
                    run_id,
                    call_id,
                    bot_id,
                    group_id,
                    tool,
                    payload,
                    channel_id,
                    created.isoformat(),
                    expires.isoformat(),
                ),
            )
            row = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)).fetchone()
        assert row is not None
        return _row_to_approval(row)

    def get(self, approval_id: str) -> Approval | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)).fetchone()
        return _row_to_approval(row) if row else None

    def get_by_call_id(self, call_id: str) -> Approval | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_approvals WHERE call_id = ? ORDER BY created_at DESC LIMIT 1",
                (call_id,),
            ).fetchone()
        return _row_to_approval(row) if row else None

    def list(self, *, status: str | None = None, limit: int = 100) -> list[Approval]:
        self.expire_due()
        query = "SELECT * FROM pending_approvals"
        values: list[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            values.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_approval(row) for row in rows]

    def expire_due(self) -> int:
        now = _now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE pending_approvals SET status = 'expired', resolved_at = ? "
                "WHERE status = 'pending' AND expires_at <= ?",
                (now, now),
            )
        return cursor.rowcount

    def resolve(
        self,
        *,
        approval_id: str | None = None,
        call_id: str | None = None,
        approved: bool,
        resolved_by: str = OWNER,
    ) -> tuple[Approval | None, str]:
        """Resolve an approval. Returns ``(approval, reason)``.

        ``reason`` is ``ok``, ``not_found``, ``forbidden``, ``expired`` or ``conflict``.
        """
        if resolved_by != OWNER:
            return None, "forbidden"
        self.expire_due()
        with self._connect() as conn:
            if approval_id is not None:
                row = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)).fetchone()
            elif call_id is not None:
                row = conn.execute(
                    "SELECT * FROM pending_approvals WHERE call_id = ? ORDER BY created_at DESC LIMIT 1",
                    (call_id,),
                ).fetchone()
            else:
                return None, "not_found"
            if row is None:
                return None, "not_found"
            if row["status"] == "expired":
                return _row_to_approval(row), "expired"
            if row["status"] != "pending":
                return _row_to_approval(row), "conflict"
            status = "approved" if approved else "denied"
            conn.execute(
                "UPDATE pending_approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
                (status, _now().isoformat(), resolved_by, row["id"]),
            )
            updated = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (row["id"],)).fetchone()
        assert updated is not None
        return _row_to_approval(updated), "ok"
