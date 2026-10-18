"""Configuration package for 小巧.

Public surface:

* :mod:`xiaoqiao.config.schema` — the typed model (``Settings`` and friends)
* :mod:`xiaoqiao.config.reader` — ``config.toml`` → ``Settings``
* :mod:`xiaoqiao.config.writer` — ``Settings`` → ``config.toml`` (comment preserving)
* :mod:`xiaoqiao.config.migrate` — legacy ``settings.json`` → ``Settings``

``xiaoqiao.settings`` stays the facade everything else imports.
"""

from __future__ import annotations

from xiaoqiao.config.migrate import migrate_legacy_settings
from xiaoqiao.config.reader import settings_from_mapping
from xiaoqiao.config.schema import (
    DEFAULT_MODEL,
    LimitsSettings,
    LoopControlSettings,
    ModelSettings,
    PermissionRule,
    PermissionSettings,
    ProviderSettings,
    ServiceSettings,
    Settings,
    ThinkingSettings,
    split_alias,
)
from xiaoqiao.config.writer import render, write_config

__all__ = [
    "DEFAULT_MODEL",
    "LimitsSettings",
    "LoopControlSettings",
    "ModelSettings",
    "PermissionRule",
    "PermissionSettings",
    "ProviderSettings",
    "ServiceSettings",
    "Settings",
    "ThinkingSettings",
    "migrate_legacy_settings",
    "render",
    "settings_from_mapping",
    "split_alias",
    "write_config",
]
