"""Artifacts: files produced in a bot's workspace during a run.

Scanning only runs when the bot has an explicit workspace, so the default
"current directory" mode does not index the whole repository on every turn.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".dsh-memory",
}

MAX_FILES = 50
MAX_FILE_BYTES = 50 * 1024 * 1024
#: How far before the run's start timestamp to look. Guards against filesystem
#: mtime granularity making a just-written file look older than the run.
MTIME_TOLERANCE_SECONDS = 1.0


@dataclass(frozen=True)
class Artifact:
    id: str
    bot_id: str
    run_id: str | None
    path: str
    mime: str | None
    size: int | None
    created_at: str


def _row_to_artifact(row: sqlite3.Row) -> Artifact:
    return Artifact(
        id=row["id"],
        bot_id=row["bot_id"],
        run_id=row["run_id"],
        path=row["path"],
        mime=row["mime"],
        size=row["size"],
        created_at=row["created_at"],
    )


def artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "botId": artifact.bot_id,
        "runId": artifact.run_id,
        "path": artifact.path,
        "mime": artifact.mime,
        "size": artifact.size,
        "createdAt": artifact.created_at,
    }


class ArtifactRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def get(self, artifact_id: str) -> Artifact | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        return _row_to_artifact(row) if row else None

    def list(
        self,
        *,
        bot_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[Artifact]:
        query = "SELECT * FROM artifacts"
        clauses: list[str] = []
        values: list[Any] = []
        if bot_id is not None:
            clauses.append("bot_id = ?")
            values.append(bot_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            values.append(run_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        return [_row_to_artifact(row) for row in rows]

    def record(
        self,
        bot_id: str,
        path: str,
        *,
        run_id: str | None = None,
        size: int | None = None,
    ) -> Artifact:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM artifacts WHERE bot_id = ? AND path = ?",
                (bot_id, path),
            ).fetchone()
            if existing is not None:
                if run_id is not None:
                    conn.execute("UPDATE artifacts SET run_id = ? WHERE id = ?", (run_id, existing["id"]))
                    existing = conn.execute("SELECT * FROM artifacts WHERE id = ?", (existing["id"],)).fetchone()
                assert existing is not None
                return _row_to_artifact(existing)

            artifact_id = f"art_{uuid.uuid4().hex[:12]}"
            mime, _ = mimetypes.guess_type(path)
            conn.execute(
                "INSERT INTO artifacts (id, bot_id, run_id, path, mime, size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, bot_id, run_id, path, mime, size, datetime.now(UTC).isoformat()),
            )
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        assert row is not None
        return _row_to_artifact(row)

    def scan_workspace(
        self,
        bot_id: str,
        workspace: str | Path,
        *,
        since: datetime,
        run_id: str | None = None,
    ) -> list[Artifact]:
        """Index files modified at/after ``since``; returns only newly indexed ones.

        The cutoff is pulled back by :data:`MTIME_TOLERANCE_SECONDS`: a file written
        in the same instant the run started can come back from ``stat`` with an mtime
        a hair earlier than the Python-side timestamp (filesystem granularity vs.
        float conversion), which made the scan miss the files the turn just produced.
        """
        root = Path(workspace)
        if not root.is_dir():
            return []
        cutoff = since.timestamp() - MTIME_TOLERANCE_SECONDS
        discovered: list[Artifact] = []
        for current, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not name.startswith(".")]
            for name in files:
                if len(discovered) >= MAX_FILES:
                    return discovered
                if name.startswith("."):
                    continue
                full = Path(current) / name
                try:
                    stat = full.stat()
                except OSError:
                    continue
                if stat.st_mtime < cutoff or stat.st_size > MAX_FILE_BYTES:
                    continue
                relative = str(full.relative_to(root))
                artifact = self.record(bot_id, relative, run_id=run_id, size=stat.st_size)
                if artifact not in discovered:
                    discovered.append(artifact)
        return discovered
