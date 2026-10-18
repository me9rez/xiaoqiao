"""Per-bot capability switches.

A capability is an MCP server (``mcp:<server>``) that a bot may use.  Rows are
stored only when they **differ from the default**, and the default is "on": MCP
servers were globally available before this table existed, so flipping the
default to off would silently take tools away from every existing bot.  The bot
editor can therefore disable a capability per bot without a migration step.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from xiaoqiao import store

logger = logging.getLogger(__name__)

KIND_MCP = "mcp"
KIND_SKILL = "skill"


def capability_id(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def split_capability(capability: str) -> tuple[str, str]:
    kind, _, name = capability.partition(":")
    return (kind, name) if name else ("", capability)


class CapabilityRepository:
    """Reads and writes the ``bot_capabilities`` overrides."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = db_path
        store.init_db(self._path)

    def _connect(self) -> Any:
        return store.connect(self._path)

    def overrides(self, bot_id: str) -> dict[str, bool]:
        """Explicit per-bot switches; capabilities absent here keep the default."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT capability, enabled FROM bot_capabilities WHERE bot_id = ?",
                (bot_id,),
            ).fetchall()
        return {row["capability"]: bool(row["enabled"]) for row in rows}

    def is_enabled(self, bot_id: str, capability: str) -> bool:
        return self.overrides(bot_id).get(capability, True)

    def set_enabled(self, bot_id: str, capability: str, enabled: bool) -> None:
        if not bot_id:
            raise ValueError("botId must not be empty")
        if not capability:
            raise ValueError("capability must not be empty")
        # Storing the default as an explicit row would make later default changes
        # retroactive; drop the row instead so "default" stays the default.
        if enabled:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM bot_capabilities WHERE bot_id = ? AND capability = ?",
                    (bot_id, capability),
                )
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO bot_capabilities (bot_id, capability, enabled) VALUES (?, ?, ?) "
                "ON CONFLICT(bot_id, capability) DO UPDATE SET enabled = excluded.enabled",
                (bot_id, capability, 0),
            )

    def disabled_mcp_servers(self, bot_id: str) -> set[str]:
        """MCP servers this bot must not see (used to filter its tool list)."""
        return {
            split_capability(capability)[1]
            for capability, enabled in self.overrides(bot_id).items()
            if not enabled and split_capability(capability)[0] == KIND_MCP
        }


def describe(bot_id: str, *, connectors: list[dict[str, Any]], repo: CapabilityRepository) -> list[dict[str, Any]]:
    """Merge the available MCP servers with this bot's switches."""
    overrides = repo.overrides(bot_id)
    items: list[dict[str, Any]] = []
    for connector in connectors:
        name = str(connector.get("name") or "")
        if not name:
            continue
        capability = capability_id(KIND_MCP, name)
        items.append(
            {
                "id": capability,
                "kind": KIND_MCP,
                "name": name,
                "label": str(connector.get("label") or name),
                "description": str(connector.get("description") or connector.get("command") or ""),
                "enabled": overrides.get(capability, True),
            }
        )
    return items


__all__ = [
    "KIND_MCP",
    "KIND_SKILL",
    "CapabilityRepository",
    "capability_id",
    "describe",
    "split_capability",
]
