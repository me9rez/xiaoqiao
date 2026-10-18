"""Unit tests for the harness-backed agent runtime, event translation, and tools."""

from __future__ import annotations

from typing import ClassVar

import pytest
from agent_framework import AgentSession
from agent_framework._middleware import FunctionInvocationContext
from agent_framework._tools import SKIP_PARSING, FunctionTool
from agent_framework._types import AgentResponseUpdate, Content, UsageDetails

from xiaoqiao.agent_runtime import AgentRuntime, dispatch_update
from xiaoqiao.config.schema import ModelSettings, ProviderSettings, Settings
from xiaoqiao.events import (
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    UsageEvent,
)
from xiaoqiao.tool_events import ToolEventMiddleware, extract_tool_result
from xiaoqiao.tools.coding_tools import _ToolResult


class _StubClient:
    """Protocol-shaped client; never actually invoked by these tests."""

    additional_properties: ClassVar[dict] = {}

    def get_response(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError


def _settings_with(context: int = 200_000, output: int = 8_000) -> Settings:
    return Settings(
        default_model="deepseek/test",
        providers={"deepseek": ProviderSettings(type="openai", base_url="https://api.deepseek.com/v1")},
        models={
            "deepseek/test": ModelSettings(
                provider="deepseek",
                model="test",
                max_context_size=context,
                max_output_size=output,
            )
        },
    )


def _build_runtime(settings: Settings | None = None) -> AgentRuntime:
    return AgentRuntime(
        client=_StubClient(),
        tools=[],
        session=AgentSession(session_id="t"),
        instructions="test",
        on_event=lambda _event: None,
        settings=settings,
    )


class TestCompactionWiring:
    """The harness silently disables compaction unless BOTH token bounds are given.

    ``_assemble_compaction`` only builds its default strategy when
    ``max_context_window_tokens`` AND ``max_output_tokens`` are both set; passing
    just the window leaves ``compaction_strategy`` as None. That regression is
    invisible at runtime, so it is pinned here.
    """

    def test_compaction_strategy_is_configured(self) -> None:
        agent = _build_runtime(_settings_with()).agent
        assert getattr(agent, "compaction_strategy", None) is not None

    def test_after_run_compaction_provider_is_wired(self) -> None:
        agent = _build_runtime(_settings_with()).agent
        providers = [type(c).__name__ for c in (agent.context_providers or [])]
        assert "CompactionProvider" in providers

    def test_output_bound_stays_below_context_window(self) -> None:
        """The harness rejects max_output_tokens >= max_context_window_tokens."""
        runtime = _build_runtime(_settings_with(context=100_000, output=8_000))
        context, output = runtime._compaction_bounds  # type: ignore[misc]
        assert context == 100_000
        assert output is not None
        assert 0 < output < context

    def test_oversized_max_tokens_is_clamped(self) -> None:
        """A misconfigured maxTokens must not disable compaction outright."""
        runtime = _build_runtime(_settings_with(context=8_000, output=64_000))
        context, output = runtime._compaction_bounds  # type: ignore[misc]
        assert context is not None
        assert output is not None
        assert 0 < output < context

    def test_no_settings_leaves_compaction_unconfigured(self) -> None:
        """Without a model config there are no bounds to apply; do not fabricate."""
        agent = _build_runtime(None).agent
        assert getattr(agent, "compaction_strategy", None) is None


class TestDispatchUpdate:
    """The harness streams AgentResponseUpdate; we translate each chunk to events."""

    def test_text_delta(self) -> None:
        events: list[object] = []
        update = AgentResponseUpdate(contents=[Content(type="text", text="hello")])
        dispatch_update(update, events.append, None)
        assert len(events) == 1
        assert isinstance(events[0], TextDeltaEvent)
        assert events[0].delta == "hello"

    def test_thinking_delta(self) -> None:
        events: list[object] = []
        update = AgentResponseUpdate(contents=[Content(type="thinking", text="thinking...")])  # type: ignore[arg-type]
        dispatch_update(update, events.append, None)
        assert len(events) == 1
        assert isinstance(events[0], ThinkingDeltaEvent)
        assert events[0].delta == "thinking..."

    def test_reasoning_content_type(self) -> None:
        """Providers normalize reasoning onto several content type names."""
        events: list[object] = []
        update = AgentResponseUpdate(contents=[Content(type="reasoning", text="why")])  # type: ignore[arg-type]
        dispatch_update(update, events.append, None)
        assert len(events) == 1
        assert isinstance(events[0], ThinkingDeltaEvent)

    def test_usage_event(self) -> None:
        events: list[object] = []
        usage = UsageDetails(
            input_token_count=10,
            output_token_count=5,
            total_token_count=15,
        )
        update = AgentResponseUpdate(contents=[Content(type="usage", usage_details=usage)])
        dispatch_update(update, events.append, None)
        assert len(events) == 1
        assert isinstance(events[0], UsageEvent)
        assert events[0].input_tokens == 10
        assert events[0].output_tokens == 5

    def test_approval_request_is_returned(self) -> None:
        events: list[object] = []
        function_call = Content(type="function_call", call_id="c1", name="place_trade", arguments="{}")
        content = Content(type="function_approval_request", function_call=function_call)
        update = AgentResponseUpdate(contents=[content])
        pending = dispatch_update(update, events.append, None)
        assert pending is not None
        assert pending.name == "place_trade"
        assert pending.call_id == "c1"


class TestExtractToolResult:
    def test_tool_result_object(self) -> None:
        text, exit_code, ok = extract_tool_result(_ToolResult(result="output", exit_code=1, ok=False))
        assert text == "output"
        assert exit_code == 1
        assert ok is False

    def test_plain_string(self) -> None:
        text, exit_code, ok = extract_tool_result("plain result")
        assert text == "plain result"
        assert exit_code is None
        assert ok is True

    def test_content_list(self) -> None:
        text, exit_code, ok = extract_tool_result([Content(type="text", text="content result")])
        assert text == "content result"
        assert exit_code is None
        assert ok is True

    def test_none_result(self) -> None:
        text, exit_code, ok = extract_tool_result(None)
        assert text == ""
        assert exit_code is None
        assert ok is True

    def test_async_iterable_is_rejected(self) -> None:
        """Silently returning empty text would masquerade as a successful result."""

        async def agen():
            yield "chunk"

        with pytest.raises(TypeError, match="async iterable"):
            extract_tool_result(agen())


class TestToolEventMiddleware:
    @pytest.mark.asyncio
    async def test_emits_tool_events(self) -> None:
        events: list[object] = []
        middleware = ToolEventMiddleware(events.append)

        async def dummy_tool() -> str:
            return "result"

        tool = FunctionTool(name="dummy", description="", func=dummy_tool, result_parser=SKIP_PARSING)
        context = FunctionInvocationContext(
            function=tool,
            arguments={"x": 1},
            metadata={"call_id": "call-123"},
        )

        async def call_next() -> None:
            context.result = await tool.invoke(arguments={"x": 1})

        await middleware.process(context, call_next)

        assert len(events) == 3
        assert isinstance(events[0], ToolCallStartEvent)
        assert events[0].call_id == "call-123"
        assert events[0].name == "dummy"
        assert isinstance(events[1], ToolExecutionStartEvent)
        assert isinstance(events[2], ToolExecutionEndEvent)
        assert events[2].result == "result"
        assert events[2].ok is True

    @pytest.mark.asyncio
    async def test_emits_error_event_on_failure(self) -> None:
        events: list[object] = []
        middleware = ToolEventMiddleware(events.append)

        async def failing_tool() -> str:
            raise RuntimeError("boom")

        tool = FunctionTool(name="fail", description="", func=failing_tool, result_parser=SKIP_PARSING)
        context = FunctionInvocationContext(
            function=tool,
            arguments={},
            metadata={"call_id": "call-456"},
        )

        async def call_next() -> None:
            context.result = await tool.invoke(arguments={})

        with pytest.raises(RuntimeError, match="boom"):
            await middleware.process(context, call_next)

        assert any(isinstance(e, ToolExecutionEndEvent) and not e.ok for e in events)

    @pytest.mark.asyncio
    async def test_emit_sink_can_be_replaced(self) -> None:
        """The runtime rebinds the sink per turn, so set_emit must take effect."""
        first: list[object] = []
        second: list[object] = []
        middleware = ToolEventMiddleware(first.append)
        middleware.set_emit(second.append)

        async def dummy_tool() -> str:
            return "ok"

        tool = FunctionTool(name="dummy", description="", func=dummy_tool, result_parser=SKIP_PARSING)
        context = FunctionInvocationContext(function=tool, arguments={}, metadata={"call_id": "c"})

        async def call_next() -> None:
            context.result = await tool.invoke(arguments={})

        await middleware.process(context, call_next)
        assert not first
        assert len(second) == 3
