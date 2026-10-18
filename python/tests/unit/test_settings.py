"""Unit tests for settings loading and client construction."""

from __future__ import annotations

from typing import cast

import pytest

from xiaoqiao.config.schema import ModelSettings, ProviderSettings, Settings
from xiaoqiao.settings import _FakeClient, build_client, effective_effort, resolve_api_key


def _settings(*, api_key: str = "fake-key", context: int = 128_000, output: int = 8_000) -> Settings:
    return Settings(
        default_model="deepseek/deepseek-chat",
        providers={
            "deepseek": ProviderSettings(
                type="openai",
                base_url="https://api.deepseek.com/v1",
                api_key=api_key,
            )
        },
        models={
            "deepseek/deepseek-chat": ModelSettings(
                provider="deepseek",
                model="deepseek-chat",
                max_context_size=context,
                max_output_size=output,
                capabilities=["thinking", "tool_use"],
                support_efforts=["high", "max"],
                default_effort="max",
            )
        },
    )


@pytest.fixture(autouse=True)
def _no_ambient_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these cases independent of whatever the host shell exports."""
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class TestBuildClient:
    def test_build_client_returns_openai_chat_completion_client(self) -> None:
        client = build_client(_settings())

        # Verify it is the full client with function invocation support.
        from agent_framework._tools import FunctionInvocationLayer
        from agent_framework_openai import OpenAIChatCompletionClient

        assert isinstance(client, OpenAIChatCompletionClient)
        assert isinstance(client, FunctionInvocationLayer)
        assert getattr(client, "model", None) == "deepseek-chat"

    def test_build_client_without_api_key_returns_fake_client(self) -> None:
        assert isinstance(build_client(_settings(api_key="")), _FakeClient)


class TestResolveApiKey:
    def test_provider_key_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
        assert resolve_api_key(_settings(api_key="from-file")) == "from-file"

    def test_api_key_env_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings(api_key="")
        settings.providers["deepseek"].api_key_env = "XQ_TEST_KEY"
        monkeypatch.setenv("XQ_TEST_KEY", "from-var")
        assert resolve_api_key(settings) == "from-var"

    def test_shell_env_is_the_last_resort(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
        assert resolve_api_key(_settings(api_key="")) == "from-env"


class TestEffectiveEffort:
    def test_model_default_effort(self) -> None:
        assert effective_effort(_settings()) == "max"

    def test_global_effort_overrides_model(self) -> None:
        settings = _settings()
        settings.thinking.effort = "high"
        assert effective_effort(settings) == "high"

    def test_disabled_thinking_yields_none(self) -> None:
        settings = _settings()
        settings.thinking.enabled = False
        assert effective_effort(settings) is None

    def test_non_reasoning_model_yields_none(self) -> None:
        settings = _settings()
        settings.models["deepseek/deepseek-chat"].capabilities = ["tool_use"]
        settings.models["deepseek/deepseek-chat"].support_efforts = []
        assert effective_effort(settings) is None


class TestFakeClient:
    @pytest.mark.asyncio
    async def test_fake_client_streaming(self) -> None:
        from agent_framework._types import Message, ResponseStream

        client = _FakeClient()
        stream = cast(ResponseStream, await client.get_response([Message(role="user", contents=["hi"])], stream=True))
        chunks = [chunk async for chunk in stream]
        assert any("Hello from fake agent" in str(chunk) for chunk in chunks)

        response = await stream.get_final_response()
        assert response.messages
        assert any(
            getattr(c, "text", "") == "Hello from fake agent! No real API key configured."
            for msg in response.messages
            for c in getattr(msg, "contents", [])
        )
