"""Settings management — reads/writes ~/.coding-agent/settings.json.

Configuration now follows a provider/model layout similar to openclaw.json:

    {
      "primaryModel": "deepseek/deepseek-v4-flash",
      "providers": {
        "deepseek": {
          "api": "openai-completions",
          "baseUrl": "https://api.deepseek.com/v1",
          "apiKey": "...",
          "models": [
            {
              "id": "deepseek-v4-flash",
              "name": "DeepSeek V4 Flash",
              "contextWindow": 128000,
              "maxTokens": 8000,
              "reasoning": true,
              "thinking_level": ["high", "max"],
              "input": ["text"]
            }
          ]
        }
      },
      "max_turns": 25
    }

Legacy top-level ``model/base_url/api_key/thinking_level/max_*_tokens`` fields are
migrated automatically.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

_SETTINGS_DIR = Path.home() / ".coding-agent"
_SETTINGS_PATH = _SETTINGS_DIR / "settings.json"


def _default_providers() -> dict[str, Any]:
    return {
        "deepseek": {
            "api": "openai-completions",
            "baseUrl": "https://api.deepseek.com/v1",
            "apiKey": "",
            "models": [
                {
                    "id": "deepseek-v4-flash",
                    "name": "DeepSeek V4 Flash",
                    "contextWindow": 128_000,
                    "maxTokens": 8_000,
                    "reasoning": True,
                    "thinking_level": ["high", "max"],
                    "input": ["text"],
                },
                {
                    "id": "deepseek-v4",
                    "name": "DeepSeek V4",
                    "contextWindow": 128_000,
                    "maxTokens": 8_000,
                    "reasoning": True,
                    "thinking_level": ["high", "max"],
                    "input": ["text"],
                },
            ],
        }
    }


@dataclass
class Settings:
    primary_model: str = "deepseek/deepseek-v4-flash"
    providers: dict[str, Any] = field(default_factory=_default_providers)
    max_turns: int = 25
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    workflow_loop: bool = True
    tool_approval: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "always_require": ["run_command", "write_file", "edit_file", "http_fetch"],
            "never_require": [],
        }
    )


def _default_settings() -> Settings:
    return Settings()


def _infer_provider(base_url: str) -> str:
    url = base_url.lower()
    if "deepseek" in url:
        return "deepseek"
    if "openai" in url:
        return "openai"
    if "minimaxi" in url:
        return "minimax"
    return "custom"


def _split_selected_model(value: str) -> tuple[str, str]:
    if "/" in value:
        provider, model = value.split("/", 1)
        return provider, model
    return "deepseek", value


def load() -> Settings:
    """Load settings from ~/.coding-agent/settings.json."""
    if not _SETTINGS_PATH.exists():
        return _default_settings()
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        s = _default_settings()
        migrated = False

        # New format
        if "primaryModel" in data:
            s.primary_model = data["primaryModel"]
        if "primary_model" in data:
            s.primary_model = data["primary_model"]
        # Keep backward compatibility during transition
        if "selectedModel" in data:
            s.primary_model = data["selectedModel"]
        if "selected_model" in data:
            s.primary_model = data["selected_model"]
        if "providers" in data:
            s.providers = data["providers"]

        # Legacy format migration
        if "providers" not in data and any(k in data for k in ("model", "base_url", "api_key")):
            provider_id = _infer_provider(data.get("base_url", ""))
            model_id = data.get("model", _split_selected_model(s.primary_model)[1])
            old_thinking = data.get("thinking_level", "")
            thinking_levels: list[str] = []
            if old_thinking and old_thinking.lower() not in ("off", ""):
                thinking_levels.append(old_thinking.lower())
            if provider_id == "deepseek":
                for lvl in ("high", "max"):
                    if lvl not in thinking_levels:
                        thinking_levels.append(lvl)
            s.providers = {
                provider_id: {
                    "api": "openai-completions",
                    "baseUrl": data.get("base_url", "https://api.deepseek.com/v1"),
                    "apiKey": data.get("api_key", ""),
                    "models": [
                        {
                            "id": model_id,
                            "name": model_id,
                            "contextWindow": data.get("max_context_tokens", 128_000),
                            "maxTokens": data.get("max_output_tokens", 8_000),
                            "reasoning": bool(thinking_levels),
                            "thinking_level": thinking_levels or ["high", "max"],
                            "input": ["text"],
                        }
                    ],
                }
            }
            s.primary_model = f"{provider_id}/{model_id}"
            migrated = True

        if "max_turns" in data:
            s.max_turns = data["max_turns"]
        if "mcpServers" in data:
            s.mcp_servers = data["mcpServers"]
        elif "mcp_servers" in data:
            s.mcp_servers = data["mcp_servers"]
        if "workflowLoop" in data:
            s.workflow_loop = bool(data["workflowLoop"])
        elif "workflow_loop" in data:
            s.workflow_loop = bool(data["workflow_loop"])
        if "toolApproval" in data:
            s.tool_approval = data["toolApproval"]
        elif "tool_approval" in data:
            s.tool_approval = data["tool_approval"]

        if migrated:
            save(s)
            logger.info("Migrated legacy settings to new provider/model format")

        return s
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load settings from %s: %s", _SETTINGS_PATH, exc)
        return _default_settings()


def save(s: Settings) -> None:
    """Save settings to ~/.coding-agent/settings.json."""
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "primaryModel": s.primary_model,
        "providers": s.providers,
        "max_turns": s.max_turns,
        "mcpServers": s.mcp_servers,
        "workflowLoop": s.workflow_loop,
        "toolApproval": s.tool_approval,
    }
    _SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_api_key(settings: Settings, model: str | None = None) -> str:
    """Return the effective API key for the given model (or primary model): provider > env."""
    provider_id, _ = _split_selected_model(model or settings.primary_model)
    provider = settings.providers.get(provider_id, {})
    return provider.get("apiKey") or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""


def model_config(settings: Settings, model: str | None = None) -> dict[str, Any] | None:
    """Return the config dict for the given model (or primary model)."""
    provider_id, model_id = _split_selected_model(model or settings.primary_model)
    provider = settings.providers.get(provider_id, {})
    for m in provider.get("models", []):
        if m.get("id") == model_id:
            return m
    return None


def thinking_level(settings: Settings, model: str | None = None) -> str | None:
    """Return the default thinking level for the given model (or primary model).

    Uses the last entry from the model's ``thinking_level`` array,
    which is assumed to be the strongest/highest level.
    """
    cfg = model_config(settings, model)
    levels = cfg.get("thinking_level") if cfg else None
    if isinstance(levels, list) and levels:
        return levels[-1]
    return None


def build_client(settings: Settings, model: str | None = None) -> object:
    """Create an LLM client for the given model (or primary model)."""
    provider_id, model_id = _split_selected_model(model or settings.primary_model)
    provider = settings.providers.get(provider_id, {})
    base_url = provider.get("baseUrl", "")
    api_key = resolve_api_key(settings, model)
    if api_key:
        from agent_framework._tools import FunctionInvocationConfiguration
        from agent_framework_openai import OpenAIChatCompletionClient

        logger.info(
            "Client: provider=%s model=%s base_url=%s",
            provider_id,
            model_id,
            base_url,
        )
        function_invocation_configuration: FunctionInvocationConfiguration = {
            "max_iterations": max(settings.max_turns, 1),
        }
        return OpenAIChatCompletionClient(
            model=model_id,
            base_url=base_url,
            api_key=api_key,
            function_invocation_configuration=function_invocation_configuration,
        )

    logger.warning("No API key found, using fake client")
    return _FakeClient()


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
