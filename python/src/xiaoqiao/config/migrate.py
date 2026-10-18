"""One-shot conversion of the legacy ``settings.json`` into the TOML model.

Accepts every historical shape the old loader understood:

* provider/model layout (``primaryModel`` + ``providers.<id>.models[]``)
* snake_case variants (``primary_model`` …)
* ``selectedModel`` / ``selected_model``
* the oldest flat layout (``model`` + ``base_url`` + ``api_key``)

Field-by-field mapping lives in ``docs/config-toml-plan.md`` §3.2.  ``workflowLoop``
is intentionally dropped: nothing has read it since the harness migration.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from xiaoqiao.config.schema import (
    DECISION_ALLOW,
    DECISION_ASK,
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_SIZE,
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


def _table(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _int_or(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(str(value))
    except TypeError, ValueError:
        return default


def _float_or(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(str(value))
    except TypeError, ValueError:
        return default


def infer_provider(base_url: str) -> str:
    """Guess a provider id from a base URL (legacy flat layout only)."""
    url = (base_url or "").lower()
    if "deepseek" in url:
        return "deepseek"
    if "openai" in url:
        return "openai"
    if "minimaxi" in url or "minimax" in url:
        return "minimax"
    return "custom"


def _model_from_legacy(alias: str, provider_id: str, raw: Mapping[str, Any]) -> ModelSettings:
    efforts = [item.lower() for item in _str_list(_first(raw, "thinking_level", "support_efforts"))]
    efforts = [item for item in efforts if item and item != "off"]
    capabilities = _str_list(raw.get("capabilities"))
    for tag in ("thinking", "tool_use"):
        if (tag == "tool_use" or raw.get("reasoning") or efforts) and tag not in capabilities:
            capabilities.append(tag)
    for tag in _str_list(raw.get("input")):
        mapped = {"image": "image_in", "video": "video_in", "audio": "audio_in"}.get(tag.lower())
        if mapped and mapped not in capabilities:
            capabilities.append(mapped)
    return ModelSettings(
        provider=provider_id,
        model=str(_first(raw, "id", "model") or alias.split("/", 1)[-1]),
        max_context_size=_int_or(_first(raw, "max_context_size", "contextWindow"), DEFAULT_CONTEXT_SIZE),
        max_output_size=_int_or(_first(raw, "max_output_size", "maxTokens"), DEFAULT_OUTPUT_SIZE) or None,
        capabilities=capabilities,
        support_efforts=efforts,
        default_effort=_first(raw, "default_effort") or (efforts[-1] if efforts else None),
        display_name=str(_first(raw, "display_name", "name") or "") or None,
    )


def _providers_and_models(data: Mapping[str, Any]) -> tuple[dict[str, ProviderSettings], dict[str, ModelSettings]]:
    providers: dict[str, ProviderSettings] = {}
    models: dict[str, ModelSettings] = {}

    raw_providers = data.get("providers")
    if isinstance(raw_providers, Mapping) and raw_providers:
        for provider_id, raw in raw_providers.items():
            config = _table(raw)
            providers[str(provider_id)] = ProviderSettings(
                type=normalize_provider_type(str(_first(config, "api", "type") or "openai")),
                base_url=str(_first(config, "baseUrl", "base_url") or ""),
                api_key=str(_first(config, "apiKey", "api_key") or ""),
                api_key_env=str(_first(config, "apiKeyEnv", "api_key_env") or "") or None,
            )
            for entry in config.get("models") or []:
                item = _table(entry)
                model_id = str(_first(item, "id", "model") or "")
                if not model_id:
                    continue
                alias = f"{provider_id}/{model_id}"
                models[alias] = _model_from_legacy(alias, str(provider_id), item)
        return providers, models

    if any(key in data for key in ("model", "base_url", "baseUrl", "api_key", "apiKey")):
        base_url = str(_first(data, "base_url", "baseUrl") or "")
        provider_id = infer_provider(base_url)
        model_id = str(_first(data, "model") or DEFAULT_MODEL.split("/", 1)[1])
        providers[provider_id] = ProviderSettings(
            type="openai",
            base_url=base_url or "https://api.deepseek.com/v1",
            api_key=str(_first(data, "api_key", "apiKey") or ""),
        )
        legacy_model = {
            "id": model_id,
            "max_context_tokens": _first(data, "max_context_tokens"),
            "max_output_tokens": _first(data, "max_output_tokens"),
            "thinking_level": _first(data, "thinking_level"),
            "reasoning": bool(_first(data, "thinking_level")),
        }
        alias = f"{provider_id}/{model_id}"
        models[alias] = _model_from_legacy(alias, provider_id, legacy_model)

    return providers, models


def _permission_from_legacy(raw: Any) -> PermissionSettings:
    if not isinstance(raw, Mapping):
        return default_permission()
    mode = MODE_MANUAL if raw.get("enabled", True) is not False else MODE_YOLO
    never = _str_list(raw.get("never_require"))
    always = _str_list(raw.get("always_require"))
    # ``allow`` rules are written before ``ask`` rules: the legacy consumer
    # checks never_require first, and TOML matching is first-hit-wins.
    rules = [PermissionRule(decision=DECISION_ALLOW, pattern=name) for name in never]
    rules += [PermissionRule(decision=DECISION_ASK, pattern=name) for name in always]
    return PermissionSettings(mode=mode, rules=rules)


def _services_from_legacy(raw: Any) -> dict[str, ServiceSettings]:
    data = _table(raw)
    if not data:
        return {}
    return {
        "web_search": ServiceSettings(
            base_url=str(_first(data, "baseUrl", "base_url") or ""),
            api_key=str(_first(data, "apiKey", "api_key") or ""),
            provider=str(data.get("provider") or ""),
        )
    }


def migrate_legacy_settings(data: Mapping[str, Any]) -> tuple[Settings, dict[str, Any]]:
    """Convert a parsed ``settings.json`` into ``(Settings, mcp_servers)``."""
    providers, models = _providers_and_models(data)

    default_model = str(
        _first(data, "primaryModel", "primary_model", "selectedModel", "selected_model", "default_model") or ""
    )
    if not default_model:
        default_model = next(iter(models), DEFAULT_MODEL)

    settings = Settings(
        default_model=default_model,
        providers=providers,
        models=models,
        thinking=ThinkingSettings(),
        loop_control=LoopControlSettings(
            max_steps_per_turn=_int_or(_first(data, "max_turns", "maxStepsPerTurn"), 25),
        ),
        limits=LimitsSettings(
            daily_token_budget=_int_or(_first(data, "dailyTokenBudget", "daily_token_budget"), 0),
            daily_budget_usd=_float_or(_first(data, "dailyBudgetUsd", "daily_budget_usd"), 0.0),
            max_requests_per_minute=_int_or(_first(data, "maxRequestsPerMinute", "max_requests_per_minute"), 0),
        ),
        permission=_permission_from_legacy(_first(data, "toolApproval", "tool_approval")),
        services=_services_from_legacy(_first(data, "webSearch", "web_search")),
    )

    if "workflowLoop" in data or "workflow_loop" in data:
        logger.info("Dropping workflowLoop: nothing has read it since the harness migration")

    raw_servers = _first(data, "mcpServers", "mcp_servers")
    mcp_servers = dict(_table(raw_servers))
    return settings, mcp_servers
