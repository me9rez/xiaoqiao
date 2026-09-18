"""Unit tests for the tool-event middleware and tool result normalization."""

from __future__ import annotations

import pytest
from agent_framework._middleware import FunctionInvocationContext
from agent_framework._tools import SKIP_PARSING, FunctionTool
from agent_framework._types import AgentResponseUpdate, Content, UsageDetails

from coding_agent.agent_runtime import dispatch_update
from coding_agent.events import (
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    UsageEvent,
)
from coding_agent.tool_events import ToolEventMiddleware, extract_tool_result
from coding_agent.tools.coding_tools import _ToolResult


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
