"""On-disk state locations for 小巧.

State lives under ``~/.xiaoqiao`` by default.  ``XIAOQIAO_HOME`` overrides it
outright (the escape hatch Kimi Code offers with ``KIMI_CODE_HOME``), which is
also what the test-suite uses to keep cases hermetic.

Installs created before the rename keep their data under ``~/.coding-agent``;
that directory is used as-is while it exists and the new one does not, so
settings, sessions and skills survive the rename without a migration step.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = ".xiaoqiao"
LEGACY_DIR_NAME = ".coding-agent"
HOME_ENV_VAR = "XIAOQIAO_HOME"

CONFIG_FILE_NAME = "config.toml"
MCP_FILE_NAME = "mcp.json"
LEGACY_SETTINGS_FILE_NAME = "settings.json"


def config_dir() -> Path:
    """Return the state directory, honouring ``XIAOQIAO_HOME`` first."""
    override = os.environ.get(HOME_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    current = Path.home() / APP_DIR_NAME
    legacy = Path.home() / LEGACY_DIR_NAME
    if current.is_dir() or not legacy.is_dir():
        return current
    return legacy


def config_path() -> Path:
    """Return the TOML config file path (the authoritative one)."""
    return config_dir() / CONFIG_FILE_NAME


def mcp_config_path() -> Path:
    """Return the MCP server definitions file path."""
    return config_dir() / MCP_FILE_NAME


def legacy_settings_path() -> Path:
    """Return the pre-TOML ``settings.json`` path (read once, during migration)."""
    return config_dir() / LEGACY_SETTINGS_FILE_NAME
