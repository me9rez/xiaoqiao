"""Settings facade — reads/writes ``~/.xiaoqiao/config.toml``.

The on-disk format mirrors Kimi Code CLI's ``config.toml``:

    default_model = "deepseek/deepseek-v4-flash"

    [providers.deepseek]
    type = "openai"
    base_url = "https://api.deepseek.com/v1"
    api_key_env = "DEEPSEEK_API_KEY"

    [models."deepseek/deepseek-v4-flash"]
    provider = "deepseek"
    model = "deepseek-v4-flash"
    max_context_size = 128000
    max_output_size = 8000

    [loop_control]
    max_steps_per_turn = 25

    [[permission.rules]]
    decision = "ask"
    pattern = "run_command"

Everything that used to import this module keeps working: :func:`load`,
:func:`save`, :func:`build_client`, :func:`model_config`, :func:`resolve_api_key`
and :func:`effective_effort` are the supported surface.  A legacy
``settings.json`` is converted once, on first load, and then left in place so an
older install can still start.

See ``docs/config-toml-plan.md`` for the full field mapping.
"""

from __future__ import annotations

import json
import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from xiaoqiao.config.migrate import migrate_legacy_settings
from xiaoqiao.config.reader import (
    limits_from_mapping,
    loop_control_from_mapping,
    model_from_mapping,
    permission_from_mapping,
    provider_from_mapping,
    services_from_mapping,
    settings_from_mapping,
    thinking_from_mapping,
)
from xiaoqiao.config.schema import (
    DEFAULT_MODEL,
    ModelSettings,
    ProviderSettings,
    Settings,
    split_alias,
)
from xiaoqiao.config.writer import write_config
from xiaoqiao.paths import config_path, legacy_settings_path

logger = logging.getLogger(__name__)

#: Kept for callers that still import the private helper.
_split_selected_model = split_alias

_ENV_FALLBACK_VARS = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY")
_env_fallback_warned = False


def _quarantine(path: Path, exc: Exception) -> None:
    """Move an unparseable config aside so the gateway can still start."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    broken = path.with_name(f"{path.name}.broken-{stamp}")
    try:
        path.replace(broken)
        kept = str(broken)
    except OSError:  # pragma: no cover - only when the file vanishes mid-read
        kept = "(could not be moved)"
    logger.error("Failed to parse %s: %s; the broken file was kept at %s", path, exc, kept)


def _read(path: Path) -> Settings:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        _quarantine(path, exc)
        return Settings()
    try:
        return settings_from_mapping(data)
    except Exception:  # pragma: no cover - defensive: the reader already degrades per field
        logger.exception("Unexpected error reading %s; falling back to defaults", path)
        return Settings()


def _migrate(legacy_path: Path, target: Path) -> Settings:
    """Convert ``settings.json`` into ``config.toml`` (one shot, non-destructive)."""
    try:
        data = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read legacy settings %s: %s", legacy_path, exc)
        return Settings()
    settings, mcp_servers = migrate_legacy_settings(data)
    try:
        write_config(settings, target)
        if mcp_servers:
            from xiaoqiao.mcp_config import load_mcp_servers, save_mcp_servers

            save_mcp_servers({**mcp_servers, **load_mcp_servers()})
        logger.info("Migrated %s to %s; the JSON file is kept but no longer read", legacy_path, target)
    except OSError as exc:
        logger.warning("Could not write %s: %s", target, exc)
    return settings


def load() -> Settings:
    """Load settings from ``config.toml`` (migrating ``settings.json`` once)."""
    target = config_path()
    if target.exists():
        return _read(target)

    legacy = legacy_settings_path()
    if legacy.exists():
        return _migrate(legacy, target)

    settings = Settings()
    try:
        write_config(settings, target)
    except OSError as exc:
        logger.warning("Could not create %s: %s", target, exc)
    return settings


def save(settings: Settings) -> None:
    """Persist ``settings`` to ``config.toml`` (comment preserving, atomic)."""
    write_config(settings, config_path())


def resolve_api_key(settings: Settings, model: str | None = None) -> str:
    """Effective API key: provider ``api_key`` > ``api_key_env`` > env table > shell env."""
    provider = settings.provider(model)
    if provider is not None:
        if provider.api_key:
            return provider.api_key
        if provider.api_key_env:
            value = os.environ.get(provider.api_key_env, "").strip()
            if value:
                return value
            logger.warning("api_key_env %s is not set or empty", provider.api_key_env)
        value = provider.env_value("API_KEY")
        if value:
            return value

    global _env_fallback_warned
    for name in _ENV_FALLBACK_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            if not _env_fallback_warned:
                _env_fallback_warned = True
                logger.info("Using %s from the environment; prefer providers.<id>.api_key_env in config.toml", name)
            return value
    return ""


def model_config(settings: Settings, model: str | None = None) -> ModelSettings | None:
    """Return the model entry for the given alias (or ``default_model``)."""
    return settings.model(model)


def effective_effort(settings: Settings, model: str | None = None) -> str | None:
    """Thinking effort for a model, or ``None`` when Thinking stays off."""
    return settings.effective_effort(model)


def build_client(settings: Settings, model: str | None = None) -> object:
    """Create an LLM client for the given model (or ``default_model``)."""
    alias = model or settings.default_model
    cfg = settings.model(alias)
    provider: ProviderSettings | None = settings.provider(alias)
    model_id = cfg.model if cfg is not None else split_alias(alias)[1]
    base_url = ""
    if provider is not None:
        base_url = provider.base_url or provider.env_value("BASE_URL")
        if provider.type not in ("openai", "openai_responses"):
            logger.warning("Provider type %r is not implemented; using the OpenAI-compatible client", provider.type)

    api_key = resolve_api_key(settings, alias)
    if api_key:
        from agent_framework._tools import FunctionInvocationConfiguration
        from agent_framework_openai import OpenAIChatCompletionClient

        logger.info("Client: provider=%s model=%s base_url=%s", cfg.provider if cfg else "", model_id, base_url)
        function_invocation_configuration: FunctionInvocationConfiguration = {
            "max_iterations": max(settings.loop_control.max_steps_per_turn, 1),
        }
        return OpenAIChatCompletionClient(
            model=model_id,
            base_url=base_url,
            api_key=api_key,
            function_invocation_configuration=function_invocation_configuration,
        )

    logger.warning("No API key found, using fake client")
    return _FakeClient()


#: Legacy camelCase keys the gateway still accepts from an older frontend.
_LEGACY_KEYS = {
    "primaryModel": "default_model",
    "primary_model": "default_model",
    "selectedModel": "default_model",
    "selected_model": "default_model",
}


def to_wire(settings: Settings) -> dict[str, Any]:
    """Project settings onto the JSON-RPC payload (snake_case, same as the file)."""
    return {
        "default_model": settings.default_model,
        "providers": {name: asdict(provider) for name, provider in settings.providers.items()},
        "models": {alias: asdict(model) for alias, model in settings.models.items()},
        "thinking": asdict(settings.thinking),
        "loop_control": asdict(settings.loop_control),
        "limits": asdict(settings.limits),
        "permission": {
            "mode": settings.permission.mode,
            "dangerous_command_guard": settings.permission.dangerous_command_guard,
            "rules": [asdict(rule) for rule in settings.permission.rules],
        },
        "services": {name: asdict(service) for name, service in settings.services.items()},
    }


def apply_update(settings: Settings, patch: Mapping[str, Any]) -> Settings:
    """Apply a partial update from the UI; legacy camelCase keys are tolerated.

    Each section present in ``patch`` replaces the corresponding one wholesale,
    which is exactly how the settings store sends it (``{...settings, ...partial}``).
    """
    data = {_LEGACY_KEYS.get(str(key), str(key)): value for key, value in patch.items()}
    default_model = data.get("default_model")
    if isinstance(default_model, str) and default_model:
        settings.default_model = default_model
    if isinstance(data.get("providers"), Mapping):
        settings.providers = {
            str(name): provider_from_mapping(str(name), raw) for name, raw in data["providers"].items()
        }
    if isinstance(data.get("models"), Mapping):
        models: dict[str, ModelSettings] = {}
        for alias, raw in data["models"].items():
            model = model_from_mapping(str(alias), raw)
            if model is not None:
                models[str(alias)] = model
        settings.models = models
    if "thinking" in data:
        settings.thinking = thinking_from_mapping(data["thinking"])
    if "loop_control" in data:
        settings.loop_control = loop_control_from_mapping(data["loop_control"])
    if "limits" in data:
        settings.limits = limits_from_mapping(data["limits"])
    if "permission" in data:
        settings.permission = permission_from_mapping(data["permission"])
    if "services" in data:
        settings.services = services_from_mapping(data["services"])
    if "max_turns" in data:
        try:
            settings.loop_control.max_steps_per_turn = int(data["max_turns"])
        except TypeError, ValueError:
            logger.warning("Ignoring non-numeric max_turns: %r", data["max_turns"])
    return settings


class _FakeClient:
    """Minimal fake for exercising the event pipeline without a real LLM.

    ``additional_properties`` is required by the ``SupportsChatGetResponse``
    protocol; without it the framework treats the client as not tool-capable and
    silently skips the function-invocation loop.
    """

    additional_properties: ClassVar[dict[str, Any]] = {}

    async def get_response(
        self,
        messages: list[object],
        *,
        stream: bool = True,
        options: object = None,
        **kwargs: object,
    ) -> object:
        """Return a canned response.

        ``**kwargs`` absorbs the extras the framework forwards to chat clients
        (``compaction_strategy``, ``tokenizer``, ...) so the signature stays
        compatible as the framework evolves.
        """
        del messages, options, kwargs
        from agent_framework._types import ChatResponse, ChatResponseUpdate, Content, Message, ResponseStream

        if stream:

            async def _stream():
                yield ChatResponseUpdate(contents=[Content(type="text", text="Hello from fake agent! ")])
                yield ChatResponseUpdate(contents=[Content(type="text", text="No real API key configured.")])
                yield ChatResponseUpdate(finish_reason="stop")

            async def _finalizer(updates):
                texts = [u.text for u in updates if u.text]
                contents = [Content(type="text", text="".join(texts))]
                return ChatResponse(messages=[Message(role="assistant", contents=contents)], finish_reason="stop")

            return ResponseStream(_stream(), finalizer=_finalizer)

        return ChatResponse(
            messages=[Message(role="assistant", contents=[Content(type="text", text="Hello from fake client!")])],
            finish_reason="stop",
        )


__all__ = [
    "DEFAULT_MODEL",
    "ModelSettings",
    "Settings",
    "build_client",
    "effective_effort",
    "load",
    "model_config",
    "resolve_api_key",
    "save",
]
