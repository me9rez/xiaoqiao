"""Run lifecycle: queue, execute, cancel and persist.

A run is the only unit of execution in 小巧.  Gateways, routines and channel
adapters all funnel into :class:`RunManager.submit`; the manager keeps one
FIFO per session, records every transition and publishes run-scoped events.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoqiao import store
from xiaoqiao.runtime.bus import EventBus, RuntimeEvent

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})


@dataclass(frozen=True)
class RunRequest:
    bot_id: str
    session_id: str
    text: str
    trigger: str = "web"
    group_id: str | None = None
    reply_to_message: str | None = None
    parent_run_id: str | None = None
    hop: int = 0
    user_id: str = "owner"


@dataclass(frozen=True)
class RunResult:
    status: str = "done"
    text: str = ""
    error: str | None = None


Execute = Callable[[RunRequest, str], Awaitable[RunResult]]


@dataclass(frozen=True)
class RunRecord:
    id: str
    bot_id: str
    session_id: str | None
    group_id: str | None
    trigger: str
    status: str
    hop: int
    error: str | None
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=row["id"],
        bot_id=row["bot_id"],
        session_id=row["session_id"],
        group_id=row["group_id"],
        trigger=row["trigger"],
        status=row["status"],
        hop=row["hop"],
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )


class RunManager:
    """Owns run tasks and their persisted state."""

    def __init__(
        self,
        execute: Execute,
        *,
        db_path: str | Path | None = None,
        bus: EventBus | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self._execute = execute
        self._path = db_path
        self._bus = bus or EventBus()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._futures: dict[str, asyncio.Future[str]] = {}
        store.init_db(self._path)

    @property
    def bus(self) -> EventBus:
        return self._bus

    def _connect(self):
        return store.connect(self._path)

    # ── public API ────────────────────────────────────────────────

    async def submit(self, request: RunRequest) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, bot_id, session_id, group_id, trigger, reply_to_message, "
                "parent_run_id, hop, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
                (
                    run_id,
                    request.bot_id,
                    request.session_id,
                    request.group_id,
                    request.trigger,
                    request.reply_to_message,
                    request.parent_run_id,
                    request.hop,
                    _now(),
                ),
            )
        self._futures[run_id] = asyncio.get_running_loop().create_future()
        self._tasks[run_id] = asyncio.create_task(self._run(run_id, request), name=f"run:{run_id}")
        return run_id

    async def wait(self, run_id: str, timeout: float | None = None) -> str:
        future = self._futures.get(run_id)
        if future is None:
            raise KeyError(f"unknown run: {run_id}")
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)

    async def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row else None

    def list(
        self,
        *,
        bot_id: str | None = None,
        group_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        query = "SELECT * FROM runs"
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in (("bot_id", bot_id), ("group_id", group_id), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_run(row) for row in rows]

    # ── internals ─────────────────────────────────────────────────

    def _set_status(self, run_id: str, status: str, *, error: str | None = None) -> None:
        now = _now()
        with self._connect() as conn:
            if status == "running":
                conn.execute(
                    "UPDATE runs SET status = ?, started_at = ? WHERE id = ?",
                    (status, now, run_id),
                )
            elif status in TERMINAL_STATUSES:
                conn.execute(
                    "UPDATE runs SET status = ?, ended_at = ?, error = ? WHERE id = ?",
                    (status, now, error, run_id),
                )
            else:
                conn.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))

    def _publish(self, type_: str, request: RunRequest, run_id: str, **data: Any) -> None:
        self._bus.publish(
            RuntimeEvent(
                type=type_,
                run_id=run_id,
                bot_id=request.bot_id,
                session_id=request.session_id,
                group_id=request.group_id,
                data=data,
            )
        )

    async def _run(self, run_id: str, request: RunRequest) -> None:
        lock = self._locks.setdefault(request.session_id, asyncio.Lock())
        status = "failed"
        error: str | None = None
        try:
            async with lock, self._semaphore:
                self._set_status(run_id, "running")
                self._publish("run_started", request, run_id)
                result = await self._execute(request, run_id)
                status = result.status if result.status in TERMINAL_STATUSES else "done"
                error = result.error
        except asyncio.CancelledError:
            status = "cancelled"
            self._publish("run_cancelled", request, run_id)
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            status = "failed"
            error = str(exc)
        finally:
            self._set_status(run_id, status, error=error)
            self._publish("run_finished", request, run_id, status=status, error=error)
            future = self._futures.get(run_id)
            if future is not None and not future.done():
                future.set_result(status)
            self._tasks.pop(run_id, None)


class RunRepository:
    """Record-only run persistence used by the gateway's in-place execution.

    ``RunManager`` owns queued execution; this repository exists so ad-hoc
    turns (direct chat, group handoff, routine delivery) still get a stable
    ``run_id`` without forcing them through the queue yet.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def begin(
        self,
        bot_id: str,
        *,
        session_id: str | None = None,
        group_id: str | None = None,
        trigger: str = "web",
        hop: int = 0,
        reply_to_message: str | None = None,
        parent_run_id: str | None = None,
    ) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, bot_id, session_id, group_id, trigger, reply_to_message, "
                "parent_run_id, hop, status, started_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)",
                (
                    run_id,
                    bot_id,
                    session_id,
                    group_id,
                    trigger,
                    reply_to_message,
                    parent_run_id,
                    hop,
                    _now(),
                    _now(),
                ),
            )
        return run_id

    def set_status(self, run_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))

    def finish(self, run_id: str, status: str = "done", *, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, ended_at = ?, error = ? WHERE id = ?",
                (status, _now(), error, run_id),
            )

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row else None

    def list(
        self,
        *,
        bot_id: str | None = None,
        group_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        query = "SELECT * FROM runs"
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in (("bot_id", bot_id), ("group_id", group_id), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_run(row) for row in rows]
