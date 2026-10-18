"""Typed configuration model for 小巧.

The on-disk format is ``~/.xiaoqiao/config.toml``, and its shape mirrors Kimi
Code CLI's ``config.toml``: snake_case keys, one table per concern, and models
keyed by *alias* (``[models."deepseek/deepseek-v4-flash"]``).

The alias is the same string the rest of the product already stores — sessions
and bots persist ``"<provider>/<model>"`` — so the flattening needs no data
migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_CONTEXT_SIZE = 128_000
DEFAULT_OUTPUT_SIZE = 8_000
DEFAULT_MAX_STEPS = 25
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_COMPACTION_ATTEMPTS = 5

THINKING = "thinking"
ALWAYS_THINKING = "always_thinking"

DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_ASK = "ask"

MODE_MANUAL = "manual"
MODE_YOLO = "yolo"
MODE_AUTO = "auto"

DEFAULT_ALWAYS_REQUIRE: tuple[str, ...] = ("run_command", "write_file", "edit_file", "http_fetch")

#: Legacy ``providers.<id>.api`` values mapped onto Kimi's provider ``type``.
API_TYPE_ALIASES: dict[str, str] = {
    "openai-completions": "openai",
    "openai-chat": "openai",
    "openai": "openai",
    "anthropic": "anthropic",
    "openai-responses": "openai_responses",
    "openai_responses": "openai_responses",
}


def split_alias(alias: str) -> tuple[str, str]:
    """Split ``provider/model`` on the first slash.

    Returns ``("", alias)`` when the alias carries no prefix, so callers can
    tell "already a bare model id" apart from a resolvable alias.
    """
    if "/" in alias:
        provider, model = alias.split("/", 1)
        return provider, model
    return "", alias


def normalize_provider_type(value: str | None) -> str:
    """Map a legacy ``api`` value onto a provider type."""
    if not value:
        return "openai"
    return API_TYPE_ALIASES.get(value.strip().lower(), "openai")


@dataclass(slots=True)
class ProviderSettings:
    """One API provider (``[providers.<name>]``)."""

    type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    api_key_env: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    custom_headers: dict[str, str] = field(default_factory=dict)

    def env_value(self, suffix: str) -> str:
        """Look a credential up in the Kimi-compatible ``env`` sub-table."""
        for key in (f"{self.type.upper()}_{suffix}", f"API_{suffix}", suffix):
            value = self.env.get(key)
            if value:
                return value
        return ""


@dataclass(slots=True)
class ModelSettings:
    """One model alias (``[models."<alias>"]``)."""

    provider: str
    model: str
    max_context_size: int = DEFAULT_CONTEXT_SIZE
    max_input_size: int | None = None
    max_output_size: int | None = None
    capabilities: list[str] = field(default_factory=list)
    support_efforts: list[str] = field(default_factory=list)
    default_effort: str | None = None
    display_name: str | None = None
    reasoning_key: str | None = None

    @property
    def supports_thinking(self) -> bool:
        return THINKING in self.capabilities or ALWAYS_THINKING in self.capabilities or bool(self.support_efforts)


@dataclass(slots=True)
class ThinkingSettings:
    enabled: bool = True
    effort: str | None = None
    keep: str | None = None


@dataclass(slots=True)
class LoopControlSettings:
    max_steps_per_turn: int = DEFAULT_MAX_STEPS
    max_attempts_per_step: int = DEFAULT_MAX_ATTEMPTS
    reserved_context_size: int | None = None
    compaction_max_attempts: int = DEFAULT_COMPACTION_ATTEMPTS


@dataclass(slots=True)
class LimitsSettings:
    """小巧 extension: daily spend caps (Kimi has no equivalent table)."""

    daily_token_budget: int = 0
    daily_budget_usd: float = 0.0
    max_requests_per_minute: int = 0


@dataclass(slots=True)
class PermissionRule:
    decision: str
    pattern: str
    reason: str | None = None
    scope: str | None = None


@dataclass(slots=True)
class PermissionSettings:
    mode: str = MODE_MANUAL
    rules: list[PermissionRule] = field(default_factory=list)
    dangerous_command_guard: bool = True

    @property
    def enabled(self) -> bool:
        return self.mode != MODE_YOLO

    def decision_for(self, tool_name: str) -> str:
        """First matching rule wins, mirroring TOML's documented ordering."""
        for rule in self.rules:
            if _pattern_matches(rule.pattern, tool_name):
                return rule.decision
        return DECISION_ASK

    def as_approval_config(self) -> dict[str, Any]:
        """Project onto the ``{enabled, always_require, never_require}`` shape.

        ``allow`` rules are listed under ``never_require`` and ``ask`` rules
        under ``always_require``; the legacy consumer checks ``never_require``
        first, which is the same precedence as writing allow before ask.
        """
        ask = [rule.pattern for rule in self.rules if rule.decision == DECISION_ASK]
        allow = [rule.pattern for rule in self.rules if rule.decision == DECISION_ALLOW]
        return {"enabled": self.enabled, "always_require": ask, "never_require": allow}


def _pattern_matches(pattern: str, tool_name: str) -> bool:
    if pattern == tool_name:
        return True
    return bool(pattern.endswith("*") and tool_name.startswith(pattern[:-1]))


@dataclass(slots=True)
class ServiceSettings:
    """Entry of ``[services.<name>]`` (web search / fetch)."""

    base_url: str = ""
    api_key: str = ""
    provider: str = ""
    custom_headers: dict[str, str] = field(default_factory=dict)


def default_permission() -> PermissionSettings:
    return PermissionSettings(
        mode=MODE_MANUAL,
        rules=[PermissionRule(decision=DECISION_ASK, pattern=name) for name in DEFAULT_ALWAYS_REQUIRE],
    )


def default_providers() -> dict[str, ProviderSettings]:
    return {
        "deepseek": ProviderSettings(
            type="openai",
            base_url="https://api.deepseek.com/v1",
            api_key="",
            api_key_env="DEEPSEEK_API_KEY",
        )
    }


def default_models() -> dict[str, ModelSettings]:
    return {
        "deepseek/deepseek-v4-flash": ModelSettings(
            provider="deepseek",
            model="deepseek-v4-flash",
            max_context_size=DEFAULT_CONTEXT_SIZE,
            max_output_size=DEFAULT_OUTPUT_SIZE,
            capabilities=[THINKING, "tool_use"],
            support_efforts=["high", "max"],
            default_effort="max",
            display_name="DeepSeek V4 Flash",
        ),
        "deepseek/deepseek-v4": ModelSettings(
            provider="deepseek",
            model="deepseek-v4",
            max_context_size=DEFAULT_CONTEXT_SIZE,
            max_output_size=DEFAULT_OUTPUT_SIZE,
            capabilities=[THINKING, "tool_use"],
            support_efforts=["high", "max"],
            default_effort="max",
            display_name="DeepSeek V4",
        ),
    }


@dataclass
class Settings:
    """Everything ``config.toml`` holds, in one place."""

    default_model: str = DEFAULT_MODEL
    providers: dict[str, ProviderSettings] = field(default_factory=default_providers)
    models: dict[str, ModelSettings] = field(default_factory=default_models)
    thinking: ThinkingSettings = field(default_factory=ThinkingSettings)
    loop_control: LoopControlSettings = field(default_factory=LoopControlSettings)
    limits: LimitsSettings = field(default_factory=LimitsSettings)
    permission: PermissionSettings = field(default_factory=default_permission)
    services: dict[str, ServiceSettings] = field(default_factory=dict)

    # ── lookups ──────────────────────────────────────────────────

    def model(self, alias: str | None = None) -> ModelSettings | None:
        """Resolve an alias: exact hit first, then ``provider/model`` split."""
        name = alias or self.default_model
        if not name:
            return None
        found = self.models.get(name)
        if found is not None:
            return found
        provider, model = split_alias(name)
        for candidate in self.models.values():
            if candidate.model == model and (not provider or candidate.provider == provider):
                return candidate
        return None

    def provider(self, alias: str | None = None) -> ProviderSettings | None:
        cfg = self.model(alias)
        if cfg is None:
            return None
        return self.providers.get(cfg.provider)

    def model_alias(self, alias: str | None = None) -> str:
        """Return the canonical alias for a model string (used by the UI/wire)."""
        name = alias or self.default_model
        if name in self.models:
            return name
        cfg = self.model(name)
        if cfg is None:
            return name
        for candidate, settings in self.models.items():
            if settings is cfg:
                return candidate
        return name

    def effective_effort(self, alias: str | None = None) -> str | None:
        """Thinking effort for a model, or ``None`` when Thinking stays off."""
        if not self.thinking.enabled:
            return None
        cfg = self.model(alias)
        if cfg is None or not cfg.supports_thinking:
            return None
        return self.thinking.effort or cfg.default_effort

    def approval_config(self) -> dict[str, Any]:
        return self.permission.as_approval_config()
