"""Backup the local state directory.

Backups are plain files: the SQLite database (copied through SQLite's own
backup API so WAL contents are included), the JSONL session transcripts and
the settings file.  Restoring is intentionally just "copy them back", so this
module never deletes or rewrites the live state.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from xiaoqiao.paths import config_dir

logger = logging.getLogger(__name__)

_EXTRA_DIRS = ("sessions", "framework_sessions")
#: ``config.toml`` is authoritative; ``mcp.json`` holds server definitions and
#: ``settings.json`` is only present on installs that have not migrated yet.
_EXTRA_FILES = ("config.toml", "mcp.json", "settings.json")


def create_backup(dest: str | Path, *, source: str | Path | None = None) -> dict[str, str]:
    """Copy the live state into ``dest``; returns the created paths."""
    source_dir = Path(source) if source is not None else config_dir()
    target_dir = Path(dest)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    root = target_dir / f"xiaoqiao-backup-{stamp}"
    root.mkdir(parents=True, exist_ok=True)

    created: dict[str, str] = {}

    database = source_dir / "agent.db"
    if database.exists():
        backup_path = root / "agent.db"
        with sqlite3.connect(database) as source_conn, sqlite3.connect(backup_path) as dest_conn:
            source_conn.backup(dest_conn)
        created["database"] = str(backup_path)

    for name in _EXTRA_DIRS:
        origin = source_dir / name
        if origin.is_dir():
            destination = root / name
            shutil.copytree(origin, destination, dirs_exist_ok=True)
            created[name] = str(destination)

    for name in _EXTRA_FILES:
        origin = source_dir / name
        if origin.is_file():
            destination = root / name
            shutil.copy2(origin, destination)
            created[name] = str(destination)

    logger.info("Backup written to %s (%d items)", root, len(created))
    return created


def backup_root(dest: str | Path) -> Path:
    """Return (and create) the directory backups are written under."""
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    return target


def verify_backup(path: str | Path) -> bool:
    """Return True when the backup's database opens and has the expected schema."""
    database = Path(path) / "agent.db" if Path(path).is_dir() else Path(path)
    if not database.is_file():
        return False
    try:
        with sqlite3.connect(database) as conn:
            row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    except sqlite3.DatabaseError:
        return False
    return bool(row and row[0])


def database_size(path: str | Path) -> int:
    database = Path(path)
    return database.stat().st_size if database.is_file() else 0


__all__ = ["backup_root", "create_backup", "database_size", "verify_backup"]
