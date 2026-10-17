"""On-disk state locations for 小巧.

State lives under ``~/.xiaoqiao``.  Installs created before the rename keep
their data under ``~/.coding-agent``; that directory is used as-is while it
exists and the new one does not, so settings, sessions and skills survive the
rename without a migration step.
"""

from __future__ import annotations

from pathlib import Path

APP_DIR_NAME = ".xiaoqiao"
LEGACY_DIR_NAME = ".coding-agent"


def config_dir() -> Path:
    """Return the state directory, preferring the current name over the legacy one."""
    current = Path.home() / APP_DIR_NAME
    legacy = Path.home() / LEGACY_DIR_NAME
    if current.is_dir() or not legacy.is_dir():
        return current
    return legacy
