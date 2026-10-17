"""Unit tests for settings and client construction."""

from __future__ import annotations

from typing import cast

import pytest

from xiaoqiao.settings import Settings, _FakeClient, build_client


class TestBuildClient:
    def test_build_client_returns_openai_chat_completion_client(self) -> None:
        settings = Settings(
            primary_model="deepseek/deepseek-chat",
            providers={
                "deepseek": {
                    "api": "openai-completions",
                    "baseUrl": "https://api.deepseek.com/v1",
                    "apiKey": "fake-key",
                    "models": [
                        {
                            "id": "deepseek-chat",
                            "name": "DeepSeek Chat",
                            "contextWindow": 128_000,
                            "maxTokens": 8_000,
                            "reasoning": False,
                            "thinking_level": [],
                            "input": ["text"],
                        }
                    ],
                }
            },
        )
        client = build_client(settings)

        # Verify it is the full client with function invocation support.
        from agent_framework._tools import FunctionInvocationLayer
        from agent_framework_openai import OpenAIChatCompletionClient

        assert isinstance(client, OpenAIChatCompletionClient)
        assert isinstance(client, FunctionInvocationLayer)
        assert getattr(client, "model", None) == "deepseek-chat"

    def test_build_client_without_api_key_returns_fake_client(self) -> None:
        settings = Settings()
        # Ensure no API key is configured.
        settings.providers["deepseek"]["apiKey"] = ""
        client = build_client(settings)
        assert isinstance(client, _FakeClient)


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
