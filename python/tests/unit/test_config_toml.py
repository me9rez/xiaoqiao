"""Tests for the config.toml format: migration, round-trip, writing, resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaoqiao import settings as settings_module
from xiaoqiao.config.reader import settings_from_mapping
from xiaoqiao.config.schema import (
    DECISION_ALLOW,
    DECISION_ASK,
    LimitsSettings,
    ModelSettings,
    PermissionRule,
    PermissionSettings,
    ProviderSettings,
    Settings,
)
from xiaoqiao.config.writer import render, write_config
from xiaoqiao.mcp_config import load_mcp_servers
from xiaoqiao.paths import config_path, mcp_config_path


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
    return tmp_path


def _write_legacy(home: Path, payload: dict) -> Path:
    path = home / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ── migration matrix (docs/config-toml-plan.md §6.1) ─────────────

_PROVIDER_MODEL_LAYOUT = {
    "primaryModel": "deepseek/deepseek-v4",
    "providers": {
        "deepseek": {
            "api": "openai-completions",
            "baseUrl": "https://api.deepseek.com/v1",
            "apiKey": "sk-legacy",
            "models": [
                {
                    "id": "deepseek-v4",
                    "name": "DeepSeek V4",
                    "contextWindow": 64_000,
                    "maxTokens": 4_000,
                    "reasoning": True,
                    "thinking_level": ["high", "max"],
                    "input": ["text", "image"],
                }
            ],
        }
    },
    "max_turns": 7,
    "dailyTokenBudget": 1234,
    "dailyBudgetUsd": 1.5,
    "maxRequestsPerMinute": 9,
    "toolApproval": {"enabled": True, "always_require": ["run_command"], "never_require": ["list_files"]},
    "mcpServers": {"fetch": {"type": "stdio", "command": "npx", "args": ["-y", "server-fetch"]}},
    "webSearch": {"provider": "searxng", "baseUrl": "http://localhost:8080", "apiKey": "search-key"},
    "workflowLoop": True,
}


class TestMigration:
    def test_provider_model_layout(self, state_home: Path) -> None:
        _write_legacy(state_home, _PROVIDER_MODEL_LAYOUT)

        settings = settings_module.load()

        assert config_path().is_file()
        assert settings.default_model == "deepseek/deepseek-v4"
        provider = settings.providers["deepseek"]
        assert provider.type == "openai"
        assert provider.base_url == "https://api.deepseek.com/v1"
        assert provider.api_key == "sk-legacy"
        model = settings.models["deepseek/deepseek-v4"]
        assert model.model == "deepseek-v4"
        assert model.max_context_size == 64_000
        assert model.max_output_size == 4_000
        assert model.support_efforts == ["high", "max"]
        assert model.default_effort == "max"  # last level, as before
        assert "thinking" in model.capabilities
        assert "image_in" in model.capabilities
        assert settings.loop_control.max_steps_per_turn == 7
        assert settings.limits == LimitsSettings(
            daily_token_budget=1234, daily_budget_usd=1.5, max_requests_per_minute=9
        )
        assert settings.services["web_search"].provider == "searxng"
        assert settings.services["web_search"].api_key == "search-key"

    def test_allow_rules_are_written_before_ask_rules(self, state_home: Path) -> None:
        _write_legacy(state_home, _PROVIDER_MODEL_LAYOUT)

        decisions = [rule.decision for rule in settings_module.load().permission.rules]

        assert decisions.index(DECISION_ALLOW) < decisions.index(DECISION_ASK)

    def test_mcp_servers_move_to_mcp_json(self, state_home: Path) -> None:
        _write_legacy(state_home, _PROVIDER_MODEL_LAYOUT)

        settings_module.load()

        servers = load_mcp_servers()
        assert servers["fetch"]["command"] == "npx"
        assert servers["fetch"]["args"] == ["-y", "server-fetch"]
        assert "type" not in servers["fetch"], "type is implied by presence of command/url"
        assert mcp_config_path().is_file()

    def test_legacy_file_is_kept(self, state_home: Path) -> None:
        legacy = _write_legacy(state_home, _PROVIDER_MODEL_LAYOUT)

        settings_module.load()

        assert legacy.is_file(), "keeping settings.json keeps downgrades working"

    def test_flat_legacy_layout(self, state_home: Path) -> None:
        _write_legacy(
            state_home,
            {
                "model": "deepseek-v4",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "k",
                "thinking_level": "high",
            },
        )

        settings = settings_module.load()

        assert settings.default_model == "deepseek/deepseek-v4"
        assert settings.models["deepseek/deepseek-v4"].default_effort == "high"
        assert settings.providers["deepseek"].api_key == "k"

    def test_snake_case_layout(self, state_home: Path) -> None:
        _write_legacy(state_home, {"primary_model": "deepseek/deepseek-v4", "max_turns": 3})

        settings = settings_module.load()

        assert settings.default_model == "deepseek/deepseek-v4"
        assert settings.loop_control.max_steps_per_turn == 3

    def test_missing_config_creates_defaults(self, state_home: Path) -> None:
        settings = settings_module.load()

        assert config_path().is_file()
        assert settings.default_model in settings.models
        assert settings.permission.mode == "manual"

    def test_migration_is_idempotent(self, state_home: Path) -> None:
        _write_legacy(state_home, _PROVIDER_MODEL_LAYOUT)
        settings_module.load()
        first = config_path().read_text(encoding="utf-8")

        settings_module.load()

        assert config_path().read_text(encoding="utf-8") == first

    def test_default_model_after_migration_survives_reload(self, state_home: Path) -> None:
        _write_legacy(state_home, _PROVIDER_MODEL_LAYOUT)
        migrated = settings_module.load()
        reloaded = settings_module.load()

        assert reloaded.default_model == migrated.default_model
        assert reloaded.models.keys() == migrated.models.keys()


# ── reader / writer ──────────────────────────────────────────────


def _sample_settings() -> Settings:
    return Settings(
        default_model="deepseek/deepseek-v4",
        providers={
            "deepseek": ProviderSettings(type="openai", base_url="https://api.deepseek.com/v1", api_key="sk"),
            "local": ProviderSettings(type="openai", base_url="http://127.0.0.1:11434/v1"),
        },
        models={
            "deepseek/deepseek-v4": ModelSettings(
                provider="deepseek",
                model="deepseek-v4",
                max_context_size=64_000,
                max_output_size=4_000,
                capabilities=["thinking", "tool_use"],
                support_efforts=["high", "max"],
                default_effort="max",
                display_name="DeepSeek V4",
            ),
            "local/llama": ModelSettings(provider="local", model="llama3", max_context_size=8_192),
        },
        limits=LimitsSettings(daily_token_budget=10, daily_budget_usd=0.5, max_requests_per_minute=3),
        permission=PermissionSettings(
            mode="manual",
            rules=[
                PermissionRule(decision=DECISION_ALLOW, pattern="list_files"),
                PermissionRule(decision=DECISION_ASK, pattern="run_command"),
            ],
        ),
    )


class TestWriter:
    def test_round_trip(self) -> None:
        original = _sample_settings()

        restored = settings_from_mapping_from_text(render(original))

        assert restored.default_model == original.default_model
        assert set(restored.models) == set(original.models)
        assert restored.models["deepseek/deepseek-v4"] == original.models["deepseek/deepseek-v4"]
        assert restored.providers["local"].base_url == "http://127.0.0.1:11434/v1"
        assert [(rule.decision, rule.pattern) for rule in restored.permission.rules] == [
            (DECISION_ALLOW, "list_files"),
            (DECISION_ASK, "run_command"),
        ]

    def test_comments_and_unknown_keys_survive_a_save(self, state_home: Path) -> None:
        settings = _sample_settings()
        write_config(settings, config_path())
        text = config_path().read_text(encoding="utf-8")
        text = text.replace(
            'default_model = "deepseek/deepseek-v4"',
            '# 手写注释：这是我的默认模型\ndefault_model = "deepseek/deepseek-v4"\n\n[my_custom]\nnote = "keep me"',
        )
        config_path().write_text(text, encoding="utf-8")

        settings.default_model = "local/llama"
        write_config(settings, config_path())

        after = config_path().read_text(encoding="utf-8")
        assert "# 手写注释：这是我的默认模型" in after
        assert "[my_custom]" in after and 'note = "keep me"' in after

    def test_saving_only_touches_the_changed_line(self, state_home: Path) -> None:
        settings = _sample_settings()
        write_config(settings, config_path())
        before = config_path().read_text(encoding="utf-8").splitlines()

        settings.default_model = "local/llama"
        write_config(settings, config_path())
        after = config_path().read_text(encoding="utf-8").splitlines()

        changed = [line for line in after if line not in before]
        assert len(changed) == 1
        assert changed[0].startswith("default_model")

    def test_unchanged_settings_do_not_rewrite_the_file(self, state_home: Path) -> None:
        settings = _sample_settings()
        write_config(settings, config_path())
        stamp = config_path().stat().st_mtime_ns

        write_config(settings, config_path())

        assert config_path().stat().st_mtime_ns == stamp

    def test_write_is_atomic(self, state_home: Path) -> None:
        write_config(_sample_settings(), config_path())

        leftovers = [p.name for p in state_home.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []
        assert config_path().read_text(encoding="utf-8").endswith("\n")

    def test_new_tables_are_separated_by_a_blank_line(self, state_home: Path) -> None:
        settings = _sample_settings()
        write_config(settings, config_path())

        settings.providers["tmpcheck"] = ProviderSettings(base_url="http://127.0.0.1:9/v1", api_key_env="TMP_KEY")
        write_config(settings, config_path())

        lines = config_path().read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.startswith("[") and index > 0 and not lines[index - 1].lstrip().startswith("#"):
                assert lines[index - 1] == "", f"{line} is glued to the line above it"

    def test_table_separation_keeps_comment_blocks(self, state_home: Path) -> None:
        settings = _sample_settings()
        config_path().write_text(
            'default_model = "deepseek/deepseek-v4"\n\n# 说明：我的模型\n[models."deepseek/deepseek-v4"]\n'
            'provider = "deepseek"\nmodel = "deepseek-v4"\n',
            encoding="utf-8",
        )

        write_config(settings, config_path())

        after = config_path().read_text(encoding="utf-8")
        assert "# 说明：我的模型\n[models." in after


def settings_from_mapping_from_text(text: str) -> Settings:
    import tomllib

    return settings_from_mapping(tomllib.loads(text))


# ── gateway wire format ──────────────────────────────────────────


class TestWireFormat:
    def test_payload_uses_the_same_vocabulary_as_the_file(self) -> None:
        payload = settings_module.to_wire(_sample_settings())

        assert payload["default_model"] == "deepseek/deepseek-v4"
        assert set(payload["providers"]["deepseek"]) >= {"type", "base_url", "api_key"}
        assert payload["models"]["local/llama"]["max_context_size"] == 8_192
        assert payload["loop_control"]["max_steps_per_turn"] == 25
        assert payload["limits"]["daily_token_budget"] == 10
        assert payload["permission"]["rules"][0] == {
            "decision": "allow",
            "pattern": "list_files",
            "reason": None,
            "scope": None,
        }

    def test_round_trip_through_apply_update(self) -> None:
        original = _sample_settings()

        updated = settings_module.apply_update(Settings(), settings_module.to_wire(original))

        assert settings_module.to_wire(updated) == settings_module.to_wire(original)

    def test_legacy_camelcase_patch_is_still_accepted(self) -> None:
        settings = _sample_settings()

        settings_module.apply_update(settings, {"primaryModel": "local/llama"})

        assert settings.default_model == "local/llama"

    def test_lowering_max_turns_patch(self) -> None:
        settings = _sample_settings()

        settings_module.apply_update(settings, {"max_turns": 3})

        assert settings.loop_control.max_steps_per_turn == 3


# ── failure handling ─────────────────────────────────────────────


class TestBrokenConfig:
    def test_broken_toml_is_quarantined(self, state_home: Path, caplog: pytest.LogCaptureFixture) -> None:
        config_path().write_text("default_model = [unclosed\n", encoding="utf-8")

        settings = settings_module.load()

        assert settings.default_model == Settings().default_model
        quarantined = list(state_home.glob("config.toml.broken-*"))
        assert len(quarantined) == 1
        assert "Failed to parse" in caplog.text

    def test_wrong_types_degrade_to_defaults(self, state_home: Path) -> None:
        config_path().write_text(
            'default_model = "deepseek/deepseek-v4"\n\n[loop_control]\nmax_steps_per_turn = "many"\n',
            encoding="utf-8",
        )

        settings = settings_module.load()

        assert settings.loop_control.max_steps_per_turn == 25

    def test_readonly_directory_does_not_crash_load(self, state_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("read-only")

        monkeypatch.setattr(settings_module, "write_config", boom)

        assert settings_module.load() is not None


# ── resolution ───────────────────────────────────────────────────


class TestResolution:
    def test_exact_alias_hit(self) -> None:
        settings = _sample_settings()
        assert settings.model("local/llama") is settings.models["local/llama"]

    def test_split_fallback_for_a_bare_model_id(self) -> None:
        settings = _sample_settings()
        assert settings.model("llama3") is settings.models["local/llama"]

    def test_unknown_alias_yields_none(self) -> None:
        assert _sample_settings().model("nope/nothing") is None

    def test_alias_with_multiple_slashes_resolves_exactly(self) -> None:
        settings = _sample_settings()
        settings.models["openrouter/anthropic/claude"] = ModelSettings(provider="deepseek", model="claude")
        assert settings.model("openrouter/anthropic/claude") is settings.models["openrouter/anthropic/claude"]

    def test_permission_first_match_wins(self) -> None:
        permission = PermissionSettings(
            rules=[
                PermissionRule(decision=DECISION_ALLOW, pattern="mcp__github__*"),
                PermissionRule(decision=DECISION_ASK, pattern="write_file"),
            ]
        )
        assert permission.decision_for("mcp__github__create_issue") == DECISION_ALLOW
        assert permission.decision_for("write_file") == DECISION_ASK
        assert permission.decision_for("unknown_tool") == DECISION_ASK
        assert permission.as_approval_config() == {
            "enabled": True,
            "always_require": ["write_file"],
            "never_require": ["mcp__github__*"],
        }

    def test_yolo_mode_disables_approvals(self) -> None:
        permission = PermissionSettings(mode="yolo", rules=[])
        assert permission.as_approval_config()["enabled"] is False


class TestConfigCommand:
    def test_path_prints_both_files(self, state_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from xiaoqiao import main as main_module

        assert main_module._run_config_command(["config", "path"]) == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert Path(lines[0]) == config_path()
        assert Path(lines[1]) == mcp_config_path()

    def test_show_masks_secrets(self, state_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from xiaoqiao import main as main_module

        write_config(_sample_settings(), config_path())

        assert main_module._run_config_command(["config", "show"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["default_model"] == "deepseek/deepseek-v4"
        assert payload["providers"]["deepseek"]["api_key"] == "***"
        assert payload["providers"]["local"]["api_key"] == ""

    def test_unknown_action_exits_nonzero(self, capsys: pytest.CaptureFixture[str]) -> None:
        from xiaoqiao import main as main_module

        assert main_module._run_config_command(["config", "nope"]) == 2
        assert "unknown config action" in capsys.readouterr().err

    def test_other_arguments_are_ignored(self) -> None:
        from xiaoqiao import main as main_module

        assert main_module._run_config_command(["--web"]) is None
        assert main_module._run_config_command([]) is None


class TestHomeOverride:
    def test_env_var_wins_over_the_default_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "custom-home"
        monkeypatch.setenv("XIAOQIAO_HOME", str(target))

        settings_module.load()

        assert config_path() == target / "config.toml"
        assert config_path().is_file()

    def test_without_override_it_uses_the_home_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XIAOQIAO_HOME", raising=False)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        assert config_path() == tmp_path / ".xiaoqiao" / "config.toml"
