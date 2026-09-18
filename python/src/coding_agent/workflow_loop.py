"""Workflow-driven coding loop with framework-native function-invocation HITL.

This module replaces the previous hand-rolled Planner/Coder/Reviewer sequence
with a single :class:`agent_framework.Agent`.  Tools that declare
``approval_mode="always_require"" cause the framework's
:class:`FunctionInvocationLayer` to return a ``function_approval_request``
content instead of executing the tool.  The gateway detects that content,
emits a ``ToolApprovalRequestEvent``, and waits for the user.  On resume, a
``function_approval_response`` is appended to the transcript and the next
``agent.run()`` automatically executes the approved call and continues the
tool loop.

This avoids :class:`ToolApprovalMiddleware`, which strips the original
``function_call`` from the assistant message and breaks OpenAI-compatible
clients on resume.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from agent_framework import Agent, Content, Message
from agent_framework._tools import normalize_tools

from coding_agent.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolApprovalRequestEvent,
    ToolCallStartEvent,
    TurnEndEvent,
    UsageEvent,
)
from coding_agent.loop import ToolEventMiddleware

if TYPE_CHECKING:
    from agent_framework._clients import SupportsChatGetResponse
    from agent_framework._skills import SkillsProvider
    from agent_framework._types import AgentResponse, AgentResponseUpdate

logger = logging.getLogger(__name__)


@dataclass
class PendingApproval:
    """Workflow paused because a tool needs human approval."""

    call_id: str
    name: str
    arguments: str
    function_call: Content
    assistant_message: Message
    conversation_messages: list[Message]
    request: Content | None = None


@dataclass
class WorkflowOutput:
    """Workflow finished with final text and accumulated messages."""

    text: str
    messages: list[Message]


WorkflowResult = WorkflowOutput | PendingApproval


def _process_update(
    update: AgentResponseUpdate,
    emit: Callable[[AgentEvent], None],
    thinking_parts_out: list[str] | None,
) -> None:
    """Extract text/thinking/usage events from one AgentResponseUpdate chunk."""
    raw = getattr(update, "raw_representation", None)
    if raw is not None:
        _extract_thinking(raw, emit, thinking_parts_out)

    contents = getattr(update, "contents", None) or []
    for c in contents:
        ctype = getattr(c, "type", None)
        if ctype == "text":
            text = getattr(c, "text", "") or ""
            if text:
                emit(TextDeltaEvent(delta=text))
        elif ctype in ("thinking", "reasoning", "reasoning_content"):
            thinking = getattr(c, "text", "") or getattr(c, "thinking", "") or getattr(c, "reasoning_content", "") or ""
            if thinking:
                if thinking_parts_out is not None:
                    thinking_parts_out.append(str(thinking))
                emit(ThinkingDeltaEvent(delta=str(thinking)))
        elif ctype == "usage":
            details = getattr(c, "usage_details", None) or {}
            emit(
                UsageEvent(
                    input_tokens=details.get("input_token_count", 0) or 0,
                    output_tokens=details.get("output_token_count", 0) or 0,
                    total_tokens=details.get("total_token_count", 0) or 0,
                    cache_read_tokens=details.get("cache_read_input_token_count", 0) or 0,
                    reasoning_tokens=details.get("reasoning_output_token_count", 0) or 0,
                    details=dict(details),
                )
            )


def _extract_thinking(
    raw: Any,
    emit: Callable[[AgentEvent], None],
    thinking_parts_out: list[str] | None,
) -> None:
    """Extract provider-specific reasoning tokens from raw data."""
    # Agent-framework may wrap the underlying provider chunk in a ChatResponseUpdate
    # and put the real raw chunk in raw_representation.
    nested = getattr(raw, "raw_representation", None)
    if nested is not None and nested is not raw:
        raw = nested

    if isinstance(raw, dict):
        for choice in raw.get("choices", []):
            delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
            reasoning = delta.get("reasoning_content") if isinstance(delta, dict) else None
            if reasoning:
                reasoning_str = str(reasoning)
                if thinking_parts_out is not None:
                    thinking_parts_out.append(reasoning_str)
                emit(ThinkingDeltaEvent(delta=reasoning_str))
        return

    choices = getattr(raw, "choices", None)
    if choices is not None:
        for choice in choices:
            delta = getattr(choice, "delta", None)
            reasoning = getattr(delta, "reasoning_content", None) if delta is not None else None
            if reasoning:
                reasoning_str = str(reasoning)
                if thinking_parts_out is not None:
                    thinking_parts_out.append(reasoning_str)
                emit(ThinkingDeltaEvent(delta=reasoning_str))


def _prepare_tools(tools: list[Any], approval_enabled: bool) -> list[Any]:
    """Return a normalized tool list with approval modes applied.

    The returned list contains copies so we do not mutate singleton tools
    created by ``create_coding_tools()``.
    """
    normalized = list(normalize_tools(tools))
    if approval_enabled:
        return normalized

    result: list[Any] = []
    for raw_tool in normalized:
        tool: Any = raw_tool
        if getattr(tool, "approval_mode", None) == "always_require":
            tool = copy.copy(tool)
            tool.approval_mode = "never_require"
        result.append(tool)
    return result


def _strip_approval_wrappers(messages: list[Message]) -> list[Message]:
    """Return a copy of messages with ``function_approval_request`` wrappers removed.

    The framework appends ``function_approval_request`` contents to the
    assistant message that already contains the original ``function_call``.
    Removing the wrapper leaves the original assistant ``tool_calls`` in the
    transcript, which is what OpenAI-compatible clients need on resume.
    """
    result: list[Message] = []
    for msg in messages:
        filtered = [c for c in msg.contents if getattr(c, "type", None) != "function_approval_request"]
        if not filtered:
            continue
        if len(filtered) == len(msg.contents):
            result.append(msg)
        else:
            cloned = copy.copy(msg)
            cloned.contents = filtered
            result.append(cloned)
    return result


def _collect_approval_requests(messages: list[Message]) -> list[Content]:
    """Collect all ``function_approval_request`` contents from response messages."""
    requests: list[Content] = []
    for msg in messages:
        for content in msg.contents:
            if getattr(content, "type", None) == "function_approval_request":
                requests.append(content)
    return requests


def _synthesize_text(messages: list[Message]) -> str:
    """Combine assistant text contents into a final user-facing string."""
    parts: list[str] = []
    for msg in messages:
        if getattr(msg, "role", None) != "assistant":
            continue
        for c in getattr(msg, "contents", []) or []:
            if getattr(c, "type", None) == "text":
                text = getattr(c, "text", "") or ""
                if text:
                    parts.append(text)
    return "\n".join(parts)


async def _run_single_agent_turn(
    agent: Agent,
    messages: list[Message],
    options: dict[str, Any],
    emit: Callable[[AgentEvent], None],
    tool_event_middleware: ToolEventMiddleware | None = None,
) -> tuple[AgentResponse, list[list[str]]]:
    """Run one agent turn, streaming events and returning the final response.

    Returns ``(response, thinking_groups)`` where *thinking_groups* is a
    list-of-lists.  Each inner list holds the thinking deltas for the
    corresponding assistant message in the response.  A new group is started
    every time a ``ToolCallStartEvent`` is emitted (by the
    ``ToolEventMiddleware``), matching the boundary between separate LLM
    invocations within a single ``agent.run()`` call.
    """
    turn_thinking_groups: list[list[str]] = [[]]

    # Wrap the emit so that ToolCallStartEvent (fired by the middleware on
    # each function invocation) triggers a group split.  This is more
    # reliable than inspecting ``update.contents`` for ``function_call``
    # entries, which the agent framework does not include in stream updates.
    def _emit_with_split(event: AgentEvent) -> None:
        if isinstance(event, ToolCallStartEvent):
            turn_thinking_groups.append([])
        emit(event)

    # Point the middleware at the split-aware emit so ToolCallStartEvent
    # fired during tool execution also triggers a group boundary.
    if tool_event_middleware is not None:
        tool_event_middleware.set_emit(_emit_with_split)

    from agent_framework._types import ChatOptions

    stream = agent.run(messages, stream=True, options=cast(ChatOptions, options))
    async for update in stream:
        _process_update(update, _emit_with_split, turn_thinking_groups[-1])
    response: AgentResponse = await stream.get_final_response()

    # Restore the original emit so the next turn starts clean.
    if tool_event_middleware is not None:
        tool_event_middleware.set_emit(emit)

    return response, turn_thinking_groups


async def run_coding_workflow(
    client: SupportsChatGetResponse,
    messages: list[Message],
    tools: list[Any] | None = None,
    on_event: Callable[[AgentEvent], None] | None = None,
    *,
    max_turns: int = 25,
    system_prompt: str | None = None,
    thinking_level: str | None = None,
    skill_provider: SkillsProvider | None = None,
    mcp_tools: list[Any] | None = None,
    approval_enabled: bool = True,
    framework_session: Any | None = None,
) -> WorkflowResult | None:
    """Run the single-agent coding workflow with native framework HITL."""
    del framework_session
    return await _run_workflow(
        client=client,
        messages=messages,
        tools=tools,
        on_event=on_event,
        max_turns=max_turns,
        system_prompt=system_prompt,
        thinking_level=thinking_level,
        skill_provider=skill_provider,
        mcp_tools=mcp_tools,
        approval_enabled=approval_enabled,
    )


def _attach_thinking(
    messages: list[Message],
    thinking_groups: list[list[str]],
) -> None:
    """Persist collected thinking deltas on the corresponding assistant message.

    Mirrors the behaviour of :func:`coding_agent.loop.run_coding_agent` so that
    :func:`coding_agent.session.message_to_dict` will later write the
    ``thinking`` field back out to the persisted JSONL session file.

    A single ``agent.run()`` may yield multiple assistant messages (one per LLM
    turn — e.g. a ``function_call`` turn followed by a post-tool text turn).
    ``thinking_groups`` is a list-of-lists where each inner list contains the
    thinking deltas emitted during the corresponding LLM turn.  Each group is
    mapped to the assistant message at the same index so the loaded transcript
    preserves the same per-bubble thinking that the live stream showed.
    """
    assistant_msgs = [m for m in messages if getattr(m, "role", None) == "assistant"]
    for i, msg in enumerate(assistant_msgs):
        if i >= len(thinking_groups):
            break
        thinking_text = "".join(thinking_groups[i])
        if not thinking_text:
            continue
        additional = getattr(msg, "additional_properties", None)
        if additional is None:
            additional = {}
            object.__setattr__(msg, "additional_properties", additional)
        additional["thinking"] = thinking_text


@asynccontextmanager
async def _agent_or_fallback(
    client: SupportsChatGetResponse,
    instructions: str,
    tools: list[Any],
    context_providers: list[Any] | None,
    middleware: list[Any],
    *,
    has_mcp: bool,
    base_tools: list[Any] | None,
    approval_enabled: bool,
):
    """Create an Agent, falling back to MCP-free tools if MCP servers fail."""
    try:
        async with Agent(
            client=client,
            instructions=instructions,
            tools=tools,
            context_providers=context_providers,
            middleware=middleware,
        ) as agent:
            yield agent
    except Exception as exc:
        if has_mcp and "MCP" in str(exc):
            logger.warning("MCP server connection failed, retrying without MCP tools: %s", exc)
            fallback_tools = _prepare_tools(list(base_tools) if base_tools else [], approval_enabled)
            async with Agent(
                client=client,
                instructions=instructions,
                tools=fallback_tools,
                context_providers=context_providers,
                middleware=middleware,
            ) as agent:
                yield agent
        else:
            raise


async def _run_workflow(
    client: SupportsChatGetResponse,
    messages: list[Message],
    tools: list[Any] | None = None,
    on_event: Callable[[AgentEvent], None] | None = None,
    *,
    max_turns: int = 25,
    system_prompt: str | None = None,
    thinking_level: str | None = None,
    skill_provider: SkillsProvider | None = None,
    mcp_tools: list[Any] | None = None,
    approval_enabled: bool = True,
) -> WorkflowResult | None:
    """Core single-agent loop with approval interception."""
    emit = on_event or (lambda _event: None)

    tool_list = list(tools) if tools else []
    if mcp_tools:
        tool_list.extend(mcp_tools)
    prepared_tools = _prepare_tools(tool_list, approval_enabled)

    options: dict[str, Any] = {"allow_multiple_tool_calls": False}
    if thinking_level:
        from coding_agent.thinking import thinking_options_for_level

        options.update(thinking_options_for_level(thinking_level))

    context_providers = [skill_provider] if skill_provider is not None else None
    tool_event_middleware = ToolEventMiddleware(emit)

    instructions = system_prompt or ""
    conversation = list(messages)

    # If Agent initialisation fails due to an MCP server connection error,
    # strip MCP tools and retry so the session can still proceed.
    async with _agent_or_fallback(
        client,
        instructions,
        prepared_tools,
        context_providers,
        [tool_event_middleware],
        has_mcp=bool(mcp_tools),
        base_tools=tools,
        approval_enabled=approval_enabled,
    ) as agent:
        for _turn in range(max_turns):
            response, turn_thinking_groups = await _run_single_agent_turn(
                agent, conversation, options, emit, tool_event_middleware
            )
            _attach_thinking(response.messages, turn_thinking_groups)

            approval_requests = _collect_approval_requests(response.messages)
            if approval_requests:
                # Keep the original assistant message with function_call(s) in the transcript.
                cleaned_response_messages = _strip_approval_wrappers(response.messages)
                _attach_thinking(cleaned_response_messages, turn_thinking_groups)
                conversation.extend(cleaned_response_messages)

                request = approval_requests[0]
                function_call = getattr(request, "function_call", None)
                if function_call is None or getattr(function_call, "type", None) != "function_call":
                    emit(ErrorEvent(message="Invalid approval request: missing function_call", recoverable=False))
                    emit(DoneEvent())
                    return None

                call_id = getattr(request, "id", "") or ""
                name = getattr(function_call, "name", "") or ""
                arguments = getattr(function_call, "arguments", "{}") or "{}"

                # Do not emit ToolCallStartEvent here: the framework's
                # FunctionInvocationLayer will emit it on resume after approval.
                # Only emit the approval request so the UI can show the pending
                # tool details without creating a duplicate tool card.
                emit(ToolApprovalRequestEvent(call_id=call_id, name=name, arguments=arguments))

                assistant_message = next(
                    (msg for msg in cleaned_response_messages if getattr(msg, "role", None) == "assistant"),
                    Message(role="assistant", contents=[function_call]),
                )
                return PendingApproval(
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                    function_call=function_call,
                    assistant_message=assistant_message,
                    conversation_messages=list(conversation),
                    request=request,
                )

            # No approval required this turn: append response and finish.
            conversation.extend(response.messages)
            break

    emit(TurnEndEvent(reason="complete"))
    emit(DoneEvent())
    return WorkflowOutput(text=_synthesize_text(conversation), messages=conversation)


def resume_coding_workflow(
    pending: PendingApproval,
    approved: bool,
    framework_session: Any | None = None,
    **kwargs: Any,
) -> Awaitable[WorkflowResult | None]:
    """Resume a workflow that was paused for tool approval."""

    async def _resume() -> WorkflowResult | None:
        conversation = list(pending.conversation_messages)
        if pending.request is not None:
            response_content = pending.request.to_function_approval_response(approved=approved)
        else:
            response_content = Content.from_function_approval_response(
                id=pending.call_id,
                function_call=pending.function_call,
                approved=approved,
            )
        conversation.append(Message(role="user", contents=[response_content]))

        return await _run_workflow(
            messages=conversation,
            approval_enabled=kwargs.get("approval_enabled", True),
            **{k: v for k, v in kwargs.items() if k not in ("messages", "approval_enabled", "framework_session")},
        )

    return _resume()
