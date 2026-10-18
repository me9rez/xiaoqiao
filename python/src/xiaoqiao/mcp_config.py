"""MCP server definitions (``~/.xiaoqiao/mcp.json``).

Server definitions live in their own file, matching Kimi Code CLI: ``config.toml``
holds runtime preferences only.  The file keeps the familiar shape

    {"mcpServers": {"filesystem": {"command": "npx", "args": [...]}}}

plus ``url`` for HTTP servers and ``transport = "sse"`` for the legacy transport.
Legacy ``type`` keys (``stdio`` / ``streamable-http`` / ``sse``) are still
accepted — both on read and as an input to :func:`normalize_server`.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from xiaoqiao.paths import mcp_config_path

logger = logging.getLogger(__name__)

MCPServers = dict[str, dict[str, Any]]

_KIND_STDIO = "stdio"
_KIND_HTTP = "streamable-http"
_KIND_SSE = "sse"


def server_kind(config: Mapping[str, Any]) -> str:
    """Classify a server entry: ``stdio`` / ``streamable-http`` / ``sse``."""
    explicit = str(config.get("type") or "").strip().lower()
    if explicit in (_KIND_STDIO, _KIND_HTTP, _KIND_SSE):
        return explicit
    if str(config.get("transport") or "").strip().lower() == "sse":
        return _KIND_SSE
    if config.get("url"):
        return _KIND_HTTP
    return _KIND_STDIO


def normalize_server(config: Mapping[str, Any]) -> dict[str, Any]:
    """Rewrite a server entry into the on-disk shape (presence-based)."""
    kind = server_kind(config)
    result: dict[str, Any] = {key: value for key, value in config.items() if key != "type"}
    if kind == _KIND_SSE:
        result["transport"] = "sse"
    else:
        result.pop("transport", None)
    return result


def load_mcp_servers(path: str | Path | None = None) -> MCPServers:
    """Read ``mcp.json``; a missing or broken file yields an empty mapping."""
    target = Path(path) if path is not None else mcp_config_path()
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", target, exc)
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, Mapping):
        logger.warning("%s has no 'mcpServers' object", target)
        return {}
    return {str(name): dict(config) for name, config in servers.items() if isinstance(config, Mapping)}


def save_mcp_servers(servers: Mapping[str, Any], path: str | Path | None = None) -> None:
    """Write ``mcp.json`` atomically."""
    target = Path(path) if path is not None else mcp_config_path()
    payload = {"mcpServers": {str(name): normalize_server(config) for name, config in servers.items()}}
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)
