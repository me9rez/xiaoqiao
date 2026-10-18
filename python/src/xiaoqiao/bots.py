"""Bot entities: persona, model, tool whitelist and workspace.

A bot is the unit of configuration in 小巧.  Every session, run and routine
belongs to exactly one bot, so these rows are the first thing the runtime
needs when it starts.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class LastBotError(ValueError):
    """Raised when deleting the only remaining bot."""


@dataclass(frozen=True)
class Bot:
    id: str
    name: str
    slug: str
    emoji: str
    persona: str
    model: str
    tools: tuple[str, ...]
    workspace: str
    created_at: str
    updated_at: str
    #: Short job title ("总管", "程序员"), shown in the sidebar and the detail drawer.
    role: str = ""
    #: One-line introduction, rendered under the bot's name.
    description: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(name: str) -> str:
    """ASCII slug; non-Latin names get an id-based fallback in ``create``."""
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-")


def _optional_column(row: sqlite3.Row, column: str) -> str:
    """Read a post-v3 column, tolerating rows selected before the migration ran."""
    try:
        return str(row[column] or "")
    except IndexError:
        return ""


def _row_to_bot(row: sqlite3.Row) -> Bot:
    try:
        tools = tuple(json.loads(row["tools_json"] or "[]"))
    except TypeError, ValueError:
        tools = ()
    return Bot(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        emoji=row["emoji"],
        persona=row["persona_md"],
        model=row["model"],
        tools=tools,
        workspace=row["workspace"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        role=_optional_column(row, "role"),
        description=_optional_column(row, "description"),
    )


def bot_to_dict(bot: Bot) -> dict[str, Any]:
    return {
        "id": bot.id,
        "name": bot.name,
        "slug": bot.slug,
        "emoji": bot.emoji,
        "persona": bot.persona,
        "model": bot.model,
        "tools": list(bot.tools),
        "workspace": bot.workspace,
        "role": bot.role,
        "description": bot.description,
        "createdAt": bot.created_at,
        "updatedAt": bot.updated_at,
    }


class BotRepository:
    """CRUD for bots, scoped to one database file (tests pass a temp path)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self):
        return store.connect(self._path)

    def list(self) -> list[Bot]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM bots ORDER BY created_at ASC").fetchall()
        return [_row_to_bot(row) for row in rows]

    def get(self, bot_id: str) -> Bot | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
        return _row_to_bot(row) if row else None

    def get_by_slug(self, slug: str) -> Bot | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM bots WHERE slug = ?", (slug,)).fetchone()
        return _row_to_bot(row) if row else None

    def _unique_slug(self, conn: sqlite3.Connection, base: str) -> str:
        candidate = base
        suffix = 2
        while conn.execute("SELECT 1 FROM bots WHERE slug = ?", (candidate,)).fetchone():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def create(
        self,
        name: str,
        *,
        emoji: str = "🤖",
        persona: str = "",
        model: str = "",
        workspace: str = "",
        tools: list[str] | None = None,
        slug: str | None = None,
        role: str = "",
        description: str = "",
    ) -> Bot:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("bot name must not be empty")
        now = _now()
        bot_id = f"bot_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            base = _slugify(slug or cleaned) or f"bot-{bot_id[-6:]}"
            final_slug = self._unique_slug(conn, base)
            conn.execute(
                """
                INSERT INTO bots (id, name, slug, emoji, persona_md, model, tools_json, workspace,
                                  role, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    cleaned,
                    final_slug,
                    emoji or "🤖",
                    persona,
                    model,
                    json.dumps(list(tools or []), ensure_ascii=False),
                    workspace,
                    role,
                    description,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
        assert row is not None
        return _row_to_bot(row)

    def update(self, bot_id: str, **changes: Any) -> Bot | None:
        allowed = {
            "name": "name",
            "emoji": "emoji",
            "persona": "persona_md",
            "model": "model",
            "workspace": "workspace",
            "role": "role",
            "description": "description",
            "slug": "slug",
        }
        updates: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in changes:
                continue
            value = changes[key]
            if key == "name":
                value = str(value).strip()
                if not value:
                    raise ValueError("bot name must not be empty")
            updates.append(f"{column} = ?")
            values.append(value)
        if "tools" in changes:
            updates.append("tools_json = ?")
            values.append(json.dumps(list(changes["tools"] or []), ensure_ascii=False))
        if not updates:
            return self.get(bot_id)
        updates.append("updated_at = ?")
        values.append(_now())
        values.append(bot_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE bots SET {', '.join(updates)} WHERE id = ?", values)
            row = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
        return _row_to_bot(row) if row else None

    def delete(self, bot_id: str) -> bool:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM bots").fetchone()["n"]
            if count <= 1:
                raise LastBotError("cannot delete the last bot")
            cursor = conn.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
        return cursor.rowcount > 0

    def ensure_default(self) -> Bot:
        """Return the first bot, creating a default one when the table is empty."""
        existing = self.list()
        if existing:
            return existing[0]
        logger.info("No bots found; creating the default Coder bot")
        return self.create("Coder", emoji="🧑‍💻", persona="")
