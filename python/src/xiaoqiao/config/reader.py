"""Parse ``config.toml`` into :class:`~xiaoqiao.config.schema.Settings`.

Reading is deliberately tolerant: a mistyped optional field degrades to its
default with a warning instead of taking the whole gateway down (see
``docs/config-toml-plan.md`` §13 — this is a documented deviation from Kimi,
which fails loudly).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from xiaoqiao.config.schema import (
    DECISION_ALLOW,
    DECISION_ASK,
    DECISION_DENY,
    MODE_MANUAL,
    MODE_YOLO,
    LimitsSettings,
    LoopControlSettings,
    ModelSettings,
    PermissionRule,
    PermissionSettings,
    ProviderSettings,
    ServiceSettings,
    Settings,
    ThinkingSettings,
    default_permission,
    normalize_provider_type,
)

logger = logging.getLogger(__name__)

_DECISIONS = (DECISION_ALLOW, DECISION_DENY, DECISION_ASK)


def _table(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return []


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except TypeError, ValueError:
        return default


def _as_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(str(value))
    except TypeError, ValueError:
        return None
    return number if number > 0 else None


def _as_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(str(value))
    except TypeError, ValueError:
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


# ── sections ─────────────────────────────────────────────────────


def provider_from_mapping(name: str, raw: Any) -> ProviderSettings:
    data = _table(raw)
    if not data:
        logger.warning("Provider %s has no table; skipping", name)
        return ProviderSettings()
    return ProviderSettings(
        type=normalize_provider_type(_as_str(_first(data, "type", "api")) or "openai"),
        base_url=_as_str(_first(data, "base_url", "baseUrl")),
        api_key=_as_str(_first(data, "api_key", "apiKey")),
        api_key_env=_as_str(_first(data, "api_key_env", "apiKeyEnv")) or None,
        env={str(k): str(v) for k, v in _table(data.get("env")).items()},
        custom_headers={str(k): str(v) for k, v in _table(_first(data, "custom_headers", "customHeaders")).items()},
    )


def model_from_mapping(alias: str, raw: Any) -> ModelSettings | None:
    data = _table(raw)
    if not data:
        logger.warning("Model %s has no table; skipping", alias)
        return None
    provider = _as_str(data.get("provider"))
    model_id = _as_str(_first(data, "model", "id"))
    if not provider or not model_id:
        logger.warning("Model %s needs both 'provider' and 'model'; skipping", alias)
        return None

    efforts = [item.lower() for item in _as_str_list(_first(data, "support_efforts", "thinking_level"))]
    capabilities = _as_str_list(data.get("capabilities"))
    if _as_bool(data.get("reasoning"), False) and "thinking" not in capabilities:
        capabilities.append("thinking")
    if efforts and "thinking" not in capabilities:
        capabilities.append("thinking")
    for tag in _as_str_list(data.get("input")):
        mapped = {"image": "image_in", "video": "video_in", "audio": "audio_in"}.get(tag.lower())
        if mapped and mapped not in capabilities:
            capabilities.append(mapped)

    default_effort = _as_str(data.get("default_effort")) or (efforts[-1] if efforts else None)
    return ModelSettings(
        provider=provider,
        model=model_id,
        max_context_size=_as_int(_first(data, "max_context_size", "contextWindow"), 128_000),
        max_input_size=_as_optional_int(data.get("max_input_size")),
        max_output_size=_as_optional_int(_first(data, "max_output_size", "maxTokens")),
        capabilities=capabilities,
        support_efforts=efforts,
        default_effort=default_effort,
        display_name=_as_str(_first(data, "display_name", "name")) or None,
        reasoning_key=_as_str(data.get("reasoning_key")) or None,
    )


def thinking_from_mapping(raw: Any) -> ThinkingSettings:
    data = _table(raw)
    if not data:
        return ThinkingSettings()
    return ThinkingSettings(
        enabled=_as_bool(data.get("enabled"), True),
        effort=_as_str(data.get("effort")) or None,
        keep=_as_str(data.get("keep")) or None,
    )


def loop_control_from_mapping(raw: Any) -> LoopControlSettings:
    data = _table(raw)
    if not data:
        return LoopControlSettings()
    return LoopControlSettings(
        max_steps_per_turn=_as_int(_first(data, "max_steps_per_turn", "max_turns"), 25),
        max_attempts_per_step=_as_int(data.get("max_attempts_per_step"), 10),
        reserved_context_size=_as_optional_int(data.get("reserved_context_size")),
        compaction_max_attempts=_as_int(data.get("compaction_max_attempts"), 5),
    )


def limits_from_mapping(raw: Any) -> LimitsSettings:
    data = _table(raw)
    if not data:
        return LimitsSettings()
    return LimitsSettings(
        daily_token_budget=_as_int(_first(data, "daily_token_budget", "dailyTokenBudget"), 0),
        daily_budget_usd=_as_float(_first(data, "daily_budget_usd", "dailyBudgetUsd"), 0.0),
        max_requests_per_minute=_as_int(_first(data, "max_requests_per_minute", "maxRequestsPerMinute"), 0),
    )


def permission_from_mapping(raw: Any) -> PermissionSettings:
    data = _table(raw)
    if not data:
        return default_permission()
    mode = _as_str(_first(data, "default_permission_mode", "mode")) or MODE_MANUAL
    if mode not in (MODE_MANUAL, MODE_YOLO, "auto"):
        logger.warning("Unknown permission mode %r; using %s", mode, MODE_MANUAL)
        mode = MODE_MANUAL

    rules: list[PermissionRule] = []
    for item in data.get("rules") or []:
        rule = _table(item)
        decision = _as_str(rule.get("decision")).strip().lower()
        pattern = _as_str(rule.get("pattern")).strip()
        if not pattern:
            logger.warning("Permission rule without a pattern; skipping")
            continue
        if decision not in _DECISIONS:
            logger.warning("Permission rule %r has unknown decision %r; treating as ask", pattern, decision)
            decision = DECISION_ASK
        rules.append(
            PermissionRule(
                decision=decision,
                pattern=pattern,
                reason=_as_str(rule.get("reason")) or None,
                scope=_as_str(rule.get("scope")) or None,
            )
        )
    guard = _as_bool(data.get("dangerous_command_guard"), True)
    return PermissionSettings(mode=mode, rules=rules, dangerous_command_guard=guard)


def services_from_mapping(raw: Any) -> dict[str, ServiceSettings]:
    services: dict[str, ServiceSettings] = {}
    for name, item in _table(raw).items():
        data = _table(item)
        services[str(name)] = ServiceSettings(
            base_url=_as_str(_first(data, "base_url", "baseUrl")),
            api_key=_as_str(_first(data, "api_key", "apiKey")),
            provider=_as_str(data.get("provider")),
            custom_headers={str(k): str(v) for k, v in _table(_first(data, "custom_headers", "customHeaders")).items()},
        )
    return services


# ── whole document ───────────────────────────────────────────────


def settings_from_mapping(data: Mapping[str, Any]) -> Settings:
    """Build a :class:`Settings` from a parsed ``config.toml`` document."""
    settings = Settings(providers={}, models={})
    settings.default_model = (
        _as_str(_first(data, "default_model", "primaryModel", "primary_model", "selectedModel", "selected_model"))
        or Settings().default_model
    )

    for name, raw in _table(data.get("providers")).items():
        settings.providers[str(name)] = provider_from_mapping(str(name), raw)

    for alias, raw in _table(data.get("models")).items():
        model = model_from_mapping(str(alias), raw)
        if model is not None:
            settings.models[str(alias)] = model

    settings.thinking = thinking_from_mapping(data.get("thinking"))
    settings.loop_control = loop_control_from_mapping(data.get("loop_control"))
    settings.limits = limits_from_mapping(data.get("limits"))
    settings.permission = permission_from_mapping(data.get("permission"))
    settings.services = services_from_mapping(data.get("services"))

    if (
        settings.models
        and settings.default_model not in settings.models
        and settings.model(settings.default_model) is None
    ):
        logger.warning("default_model %r is not defined in [models]", settings.default_model)
    if not settings.models:
        logger.warning("No [models] entries in config.toml; the gateway will fall back to the fake client")
    return settings
