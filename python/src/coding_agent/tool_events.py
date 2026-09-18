"""Tool lifecycle events as an agent-framework ``FunctionMiddleware``.

The framework's response stream carries text/thinking content but not the
tool-execution lifecycle, so this middleware emits ``tool_call_start`` /
``tool_execution_start`` / ``tool_execution_end`` for the gateway and web UI.

It is merged into the harness agent's own middleware chain (the framework
composes lists rather than replacing them), so it sits alongside the framework's
``ToolApprovalMiddleware`` without displacing it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent_framework._middleware import FunctionInvocationContext, FunctionMiddleware
from agent_framework._types import Content

from coding_agent.events import (
    AgentEvent,
    ToolCallStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)

logger = logging.getLogger(__name__)


class ToolEventMiddleware(FunctionMiddleware):
    """Emit tool lifecycle events and normalise raw tool results."""

    def __init__(self, emit: Callable[[AgentEvent], None]) -> None:
        self._emit = emit

    def set_emit(self, emit: Callable[[AgentEvent], None]) -> None:
        """Update the emit callback (the sink can change between turns)."""
        self._emit = emit

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        call_id = context.metadata.get("call_id", "")
        name = context.function.name
        arguments = _arguments_to_json(context.arguments)

        self._emit(ToolCallStartEvent(call_id=call_id, name=name, arguments=arguments))
        self._emit(ToolExecutionStartEvent(call_id=call_id, name=name))

        try:
            await call_next()
        except Exception:
            self._emit(ToolExecutionEndEvent(call_id=call_id, name=name, ok=False, error="Tool execution failed"))
            raise

        result_text, exit_code, ok = extract_tool_result(context.result)
        context.result = [Content(type="text", text=result_text)]

        self._emit(
            ToolExecutionEndEvent(
                call_id=call_id,
                name=name,
                result=result_text,
                ok=ok,
                exit_code=exit_code,
            )
        )


def _arguments_to_json(arguments: Mapping[str, Any] | Any) -> str:
    """Serialise validated tool arguments to JSON."""
    try:
        if hasattr(arguments, "model_dump"):
            payload = arguments.model_dump()  # type: ignore[union-attr]
        elif isinstance(arguments, Mapping):
            payload = dict(arguments)
        else:
            payload = {"args": str(arguments)}
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return str(arguments)


def extract_tool_result(result: Any) -> tuple[str, int | None, bool]:
    """Return ``(text, exit_code, ok)`` from a raw tool result.

    Handles ``_ToolResult``-like objects, strings, ``None``, and ``list[Content]``.

    Tools are not permitted to return a bare async iterable: there is no way to
    await one from this synchronous helper, and silently returning empty text
    would look like a successful empty result. Rejecting it surfaces the mistake
    instead of dropping output.
    """
    if hasattr(result, "__aiter__"):
        raise TypeError(
            "Tool returned an async iterable, which cannot be consumed here. "
            "Either return a str/_ToolResult, or collect the stream inside the tool."
        )

    if isinstance(result, list):
        # Default ``FunctionTool.parse_result`` output.
        text_parts = [c.text for c in result if getattr(c, "type", None) == "text" and getattr(c, "text", None)]
        return "\n".join(text_parts), None, True

    result_text = getattr(result, "result", None)
    if result_text is not None:
        exit_code = getattr(result, "exit_code", None)
        ok = getattr(result, "ok", True)
        return str(result_text), exit_code if exit_code is None or isinstance(exit_code, int) else None, bool(ok)

    if result is None:
        return "", None, True

    return str(result), None, True


__all__ = ["ToolEventMiddleware", "extract_tool_result"]
