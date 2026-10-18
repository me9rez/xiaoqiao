"""Tests for the settings UI surface: config status, strict updates, connection probe."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from xiaoqiao import settings as settings_module
from xiaoqiao.config.schema import ProviderSettings, Settings
from xiaoqiao.provider_probe import models_url, probe_headers, probe_provider


def _settings(
    *,
    base_url: str = "https://api.deepseek.com/v1",
    api_key: str = "",
    api_key_env: str | None = "DEEPSEEK_API_KEY",
) -> Settings:
    settings = Settings()
    settings.providers = {
        "deepseek": ProviderSettings(base_url=base_url, api_key=api_key, api_key_env=api_key_env),
    }
    return settings


class TestConfigStatus:
    def test_missing_key_reports_the_fake_client(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        status = settings_module.config_status(_settings())

        assert status["client"] == "fake"
        assert status["provider"] == "deepseek"
        assert status["default_model_defined"] is True
        assert status["providers"]["deepseek"]["api_key_source"] == "none"
        assert status["providers"]["deepseek"]["api_key_env_set"] is False
        assert status["config_path"].endswith("config.toml")

    def test_key_from_env_is_reported_as_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")

        status = settings_module.config_status(_settings())

        assert status["client"] == "real"
        assert status["providers"]["deepseek"]["api_key_source"] == "env"
        assert status["providers"]["deepseek"]["api_key_env_set"] is True

    def test_key_in_file_is_reported_as_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        status = settings_module.config_status(_settings(api_key="sk-file"))

        assert status["client"] == "real"
        assert status["providers"]["deepseek"]["api_key_source"] == "file"

    def test_model_count_per_provider(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))

        status = settings_module.config_status(_settings())

        assert status["providers"]["deepseek"]["model_count"] == 2

    def test_unknown_provider(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))

        status = settings_module.provider_status(_settings(), "nope")

        assert status["api_key_source"] == "missing"
        assert status["has_key"] is False


class TestStrictModelUpdate:
    def test_entry_without_provider_is_rejected(self) -> None:
        settings = Settings()
        before = len(settings.models)

        with pytest.raises(ValueError, match="缺少 provider 或 model"):
            settings_module.apply_update(
                settings,
                {"models": {"deepseek/broken": {"display_name": "未填 provider/model"}}},
            )

        assert len(settings.models) == before

    def test_valid_entries_still_pass(self) -> None:
        settings = Settings()

        settings_module.apply_update(
            settings,
            {"models": {"local/llama": {"provider": "local", "model": "llama", "display_name": "Llama"}}},
        )

        assert set(settings.models) == {"local/llama"}
        assert settings.models["local/llama"].display_name == "Llama"


def _handler(request: httpx.Request) -> httpx.Response:
    if request.headers.get("authorization") == "Bearer sk-good":
        return httpx.Response(200, json={"data": [{"id": "deepseek-v4"}, {"id": "deepseek-v4-flash"}]})
    return httpx.Response(401, text='{"error":"invalid api key"}')


class TestProbeProvider:
    async def test_success_lists_models(self) -> None:
        transport = httpx.MockTransport(_handler)

        result = await probe_provider(_settings(api_key="sk-good"), "deepseek", transport=transport)

        assert result["ok"] is True
        assert result["count"] == 2
        assert result["models"] == ["deepseek-v4", "deepseek-v4-flash"]
        assert result["url"] == "https://api.deepseek.com/v1/models"

    async def test_bad_key_reports_http_status(self) -> None:
        transport = httpx.MockTransport(_handler)

        result = await probe_provider(_settings(api_key="sk-bad"), "deepseek", transport=transport)

        assert result["ok"] is False
        assert result["status"] == 401
        assert "invalid api key" in result["error"]

    async def test_missing_key_skips_the_request(self) -> None:
        def explode(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
            raise AssertionError("no request should be sent without a key")

        result = await probe_provider(_settings(), "deepseek", transport=httpx.MockTransport(explode))

        assert result["ok"] is False
        assert "API key" in result["error"]

    async def test_unknown_provider(self) -> None:
        result = await probe_provider(_settings(), "nope", transport=httpx.MockTransport(_handler))

        assert result["ok"] is False
        assert "未找到" in result["error"]

    async def test_missing_base_url(self) -> None:
        result = await probe_provider(_settings(base_url="", api_key="sk-good"), "deepseek")

        assert result["ok"] is False
        assert "base_url" in result["error"]

    def test_anthropic_uses_v1_path_and_headers(self) -> None:
        provider = ProviderSettings(type="anthropic", base_url="https://api.anthropic.com")

        assert models_url(provider) == "https://api.anthropic.com/v1/models"
        headers = probe_headers(provider, "sk-ant")
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"]
        assert "Authorization" not in headers
