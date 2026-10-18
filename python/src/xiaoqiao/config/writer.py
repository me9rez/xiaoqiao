"""Write ``config.toml`` back, preserving comments and untouched keys.

The document is parsed with :mod:`tomlkit` and mutated in place, so a save only
touches the values that actually changed: switching models rewrites one line,
hand-written comments and unknown sections stay put, and the file keeps its
original ordering.

Writes go through a temporary file plus ``os.replace`` so a crash (or a locked
file) can never leave a half-written config behind.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomlkit

from xiaoqiao.config.schema import PermissionSettings, Settings

_HEADER = """\
# 小巧（Xiaoqiao）配置 —— 结构与字段命名对齐 Kimi Code CLI 的 config.toml。
# 手工编辑安全：保存设置时只改写发生变化的值，注释与顺序保持不变。
# 数据目录可用环境变量 XIAOQIAO_HOME 覆盖。
"""


def _unwrap(value: Any) -> Any:
    return value.unwrap() if hasattr(value, "unwrap") else value


def _set(table: Any, key: str, value: Any, *, keep_empty: bool = False) -> None:
    """Assign ``key`` only when the value really changed."""
    empty = value is None or value == "" or value == [] or value == {}
    if empty and not keep_empty:
        if key in table:
            del table[key]
        return
    if key in table and _unwrap(table[key]) == value:
        return
    table[key] = value


def _section(doc: Any, name: str) -> Any:
    existing = doc.get(name)
    if isinstance(existing, Mapping):
        return existing
    table = tomlkit.table()
    doc[name] = table
    return table


def _sync_providers(doc: Any, settings: Settings) -> None:
    providers = _section(doc, "providers")
    for name, provider in settings.providers.items():
        table = providers.get(name)
        if not isinstance(table, Mapping):
            table = tomlkit.table()
            providers[name] = table
        _set(table, "type", provider.type)
        _set(table, "base_url", provider.base_url, keep_empty=True)
        _set(table, "api_key", provider.api_key, keep_empty=True)
        _set(table, "api_key_env", provider.api_key_env)
        _set(table, "env", dict(provider.env) or None)
        _set(table, "custom_headers", dict(provider.custom_headers) or None)
    for name in [item for item in providers if item not in settings.providers]:
        del providers[name]


def _sync_models(doc: Any, settings: Settings) -> None:
    models = _section(doc, "models")
    for alias, model in settings.models.items():
        table = models.get(alias)
        if not isinstance(table, Mapping):
            table = tomlkit.table()
            models[alias] = table
        _set(table, "provider", model.provider)
        _set(table, "model", model.model)
        _set(table, "max_context_size", model.max_context_size)
        _set(table, "max_input_size", model.max_input_size)
        _set(table, "max_output_size", model.max_output_size)
        _set(table, "capabilities", list(model.capabilities) or None)
        _set(table, "support_efforts", list(model.support_efforts) or None)
        _set(table, "default_effort", model.default_effort)
        _set(table, "display_name", model.display_name)
        _set(table, "reasoning_key", model.reasoning_key)
    for alias in [item for item in models if item not in settings.models]:
        del models[alias]


def _rules_payload(permission: PermissionSettings) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for rule in permission.rules:
        item: dict[str, Any] = {"decision": rule.decision, "pattern": rule.pattern}
        if rule.scope:
            item["scope"] = rule.scope
        if rule.reason:
            item["reason"] = rule.reason
        payload.append(item)
    return payload


def _sync_permission(doc: Any, settings: Settings) -> None:
    permission = _section(doc, "permission")
    _set(permission, "default_permission_mode", settings.permission.mode)
    if not settings.permission.dangerous_command_guard:
        _set(permission, "dangerous_command_guard", False)

    payload = _rules_payload(settings.permission)
    existing = permission.get("rules")
    if existing is not None and _unwrap(existing) == payload:
        return
    if not payload:
        if "rules" in permission:
            del permission["rules"]
        return
    rules = tomlkit.aot()
    for item in payload:
        rule_table = tomlkit.table()
        for key in ("decision", "scope", "pattern", "reason"):
            if key in item:
                rule_table[key] = item[key]
        rules.append(rule_table)
    permission["rules"] = rules


def _sync_scalars(doc: Any, settings: Settings) -> None:
    thinking = _section(doc, "thinking")
    _set(thinking, "enabled", settings.thinking.enabled)
    _set(thinking, "effort", settings.thinking.effort)
    _set(thinking, "keep", settings.thinking.keep)

    loop = _section(doc, "loop_control")
    _set(loop, "max_steps_per_turn", settings.loop_control.max_steps_per_turn)
    _set(loop, "max_attempts_per_step", settings.loop_control.max_attempts_per_step)
    _set(loop, "reserved_context_size", settings.loop_control.reserved_context_size)
    _set(loop, "compaction_max_attempts", settings.loop_control.compaction_max_attempts)

    limits = _section(doc, "limits")
    _set(limits, "daily_token_budget", settings.limits.daily_token_budget)
    _set(limits, "daily_budget_usd", settings.limits.daily_budget_usd)
    _set(limits, "max_requests_per_minute", settings.limits.max_requests_per_minute)


def _sync_services(doc: Any, settings: Settings) -> None:
    services = doc.get("services")
    if services is None and not settings.services:
        return
    table = _section(doc, "services")
    for name, service in settings.services.items():
        entry = table.get(name)
        if not isinstance(entry, Mapping):
            entry = tomlkit.table()
            table[name] = entry
        _set(entry, "provider", service.provider)
        _set(entry, "base_url", service.base_url)
        _set(entry, "api_key", service.api_key)
        _set(entry, "custom_headers", dict(service.custom_headers) or None)
    for name in [item for item in table if item not in settings.services]:
        del table[name]


def _separate_tables(text: str) -> str:
    """Make sure every ``[table]`` header starts a new paragraph.

    tomlkit appends a newly created sub-table directly under the previous key, so
    adding ``[providers.openrouter]`` would otherwise produce
    ``api_key_env = "..."`` immediately followed by the header.  Idempotent, and
    it never separates a table from the comment block written right above it.
    """
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if line.startswith("[") and out and out[-1].strip() and not out[-1].lstrip().startswith("#"):
            out.append("")
        out.append(line)
    return "\n".join(out)


def render(settings: Settings, existing: str = "") -> str:
    """Return the TOML text for ``settings``, merged onto ``existing``."""
    doc = tomlkit.parse(existing) if existing.strip() else tomlkit.parse(_HEADER)
    _set(doc, "default_model", settings.default_model)
    _sync_providers(doc, settings)
    _sync_models(doc, settings)
    _sync_scalars(doc, settings)
    _sync_permission(doc, settings)
    _sync_services(doc, settings)
    return _separate_tables(tomlkit.dumps(doc))


def write_config(settings: Settings, path: Path) -> None:
    """Persist ``settings`` to ``path`` (atomic, change-aware)."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    text = render(settings, existing)
    if existing and text == existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
