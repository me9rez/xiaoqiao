"""Usage accounting and daily budgets.

Every run records its token counts here.  Budgets are enforced *before* a run
starts, based on what was already spent today, so a runaway routine stops
early instead of being discovered on the bill.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageEntry:
    id: str
    run_id: str | None
    bot_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: str


@dataclass(frozen=True)
class UsageSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    runs: int = 0
    cache_read_tokens: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _row_to_entry(row: sqlite3.Row) -> UsageEntry:
    return UsageEntry(
        id=row["id"],
        run_id=row["run_id"],
        bot_id=row["bot_id"],
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost_usd=row["cost_usd"],
        created_at=row["created_at"],
    )


class UsageRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def record(
        self,
        bot_id: str,
        model: str,
        *,
        run_id: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> UsageEntry:
        entry_id = f"use_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO usage_events (id, run_id, bot_id, model, input_tokens, output_tokens, "
                "cache_read_tokens, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    run_id,
                    bot_id,
                    model,
                    max(int(input_tokens), 0),
                    max(int(output_tokens), 0),
                    max(int(cache_read_tokens), 0),
                    float(cost_usd),
                    _now().isoformat(),
                ),
            )
            row = conn.execute("SELECT * FROM usage_events WHERE id = ?", (entry_id,)).fetchone()
        assert row is not None
        return _row_to_entry(row)

    def summary(self, *, since: datetime | None = None, bot_id: str | None = None) -> UsageSummary:
        query = "SELECT COALESCE(SUM(input_tokens), 0) AS i, COALESCE(SUM(output_tokens), 0) AS o, "
        query += "COALESCE(SUM(cache_read_tokens), 0) AS cr, COALESCE(SUM(cost_usd), 0) AS c, "
        query += "COUNT(*) AS n FROM usage_events"
        clauses: list[str] = []
        values: list[Any] = []
        if since is not None:
            clauses.append("created_at >= ?")
            values.append(since.astimezone(UTC).isoformat())
        if bot_id is not None:
            clauses.append("bot_id = ?")
            values.append(bot_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(query, values).fetchone()
        input_tokens = int(row["i"])
        output_tokens = int(row["o"])
        return UsageSummary(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=float(row["c"]),
            runs=int(row["n"]),
            cache_read_tokens=int(row["cr"]),
        )

    def today(self, *, bot_id: str | None = None, now: datetime | None = None) -> UsageSummary:
        moment = now or _now()
        start = datetime.combine(moment.astimezone(UTC).date(), time.min, tzinfo=UTC)
        return self.summary(since=start, bot_id=bot_id)

    def by_model(
        self,
        *,
        since: datetime | None = None,
        bot_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT model, COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens, "
            "COALESCE(SUM(cost_usd), 0) AS cost, COUNT(*) AS runs FROM usage_events"
        )
        clauses: list[str] = []
        values: list[Any] = []
        if since is not None:
            clauses.append("created_at >= ?")
            values.append(since.astimezone(UTC).isoformat())
        if bot_id is not None:
            clauses.append("bot_id = ?")
            values.append(bot_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " GROUP BY model ORDER BY tokens DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [
            {
                "model": row["model"],
                "tokens": int(row["tokens"]),
                "costUsd": float(row["cost"]),
                "runs": int(row["runs"]),
            }
            for row in rows
        ]

    def by_bot(
        self,
        *,
        since: datetime | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Token spend per bot, biggest first — the usage page's bot ranking."""
        query = (
            "SELECT bot_id, COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens, "
            "COALESCE(SUM(cost_usd), 0) AS cost, COUNT(*) AS runs FROM usage_events"
        )
        clauses: list[str] = []
        values: list[Any] = []
        if since is not None:
            clauses.append("created_at >= ?")
            values.append(since.astimezone(UTC).isoformat())
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " GROUP BY bot_id ORDER BY tokens DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [
            {
                "botId": row["bot_id"],
                "tokens": int(row["tokens"]),
                "costUsd": float(row["cost"]),
                "runs": int(row["runs"]),
            }
            for row in rows
        ]

    def by_day(
        self,
        *,
        since: datetime,
        bot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Per-day token totals, optionally split per bot, for the stacked chart.

        Dates are the UTC calendar day of ``created_at``; the UI groups them by
        bot so one bar per day can stack several bots.
        """
        query = (
            "SELECT substr(created_at, 1, 10) AS day, bot_id, "
            "COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens FROM usage_events"
        )
        clauses = ["created_at >= ?"]
        values: list[Any] = [since.astimezone(UTC).isoformat()]
        if bot_id is not None:
            clauses.append("bot_id = ?")
            values.append(bot_id)
        query += " WHERE " + " AND ".join(clauses)
        query += " GROUP BY day, bot_id ORDER BY day ASC"
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [{"date": row["day"], "botId": row["bot_id"], "tokens": int(row["tokens"])} for row in rows]


def budget_exceeded(
    summary: UsageSummary,
    *,
    token_budget: int,
    usd_budget: float,
) -> str | None:
    """Return a human-readable reason when today's usage is over budget."""
    if token_budget > 0 and summary.total_tokens >= token_budget:
        return f"今日 token 用量 {summary.total_tokens} 已达上限 {token_budget}"
    if usd_budget > 0 and summary.cost_usd >= usd_budget:
        return f"今日花费 ${summary.cost_usd:.4f} 已达上限 ${usd_budget:.2f}"
    return None
