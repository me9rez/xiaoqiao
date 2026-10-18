"""Agent runtime built on agent-framework's ``create_harness_agent``.

This module replaces the hand-rolled loop/HITL orchestration that used to live in
``loop.py`` and ``workflow_loop.py``.  The framework's harness factory already wires:

* function invocation (the tool loop)
* per-service-call history persistence
* context-window compaction
* tool approval (standing rules + the "don't ask again" flow)
* todo / mode / file-memory providers

What stays ours is the **event layer** (``events.py``): the framework streams
``AgentResponseUpdate`` chunks, and this module translates them into the
fine-grained ``TextDeltaEvent`` / ``ThinkingDeltaEvent`` / tool lifecycle events
that the gateway protocol and web UI consume.

The framework ``AgentSession`` is the authoritative conversation state — it must
own the ``tool_call`` / ``tool_result`` pairing that OpenAI-compatible APIs
enforce.  ``transcript`` mirrors it for persistence/display only; it is never sent
back to the model.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from agent_framework import (
    Agent,
    AgentModeProvider,
    AgentSession,
    Content,
    Message,
    create_harness_agent,
)

from xiaoqiao.events import (
    AgentEvent,
    DoneEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolApprovalRequestEvent,
    TurnEndEvent,
    UsageEvent,
)

if TYPE_CHECKING:
    from xiaoqiao.settings import Settings

logger = logging.getLogger(__name__)

# Content types providers use for reasoning/thinking. The framework normalises
# most providers onto these, so we prefer them over parsing raw payloads.
_THINKING_CONTENT_TYPES = frozenset({"thinking", "reasoning", "reasoning_content", "text_reasoning"})


@dataclass
class PendingApproval:
    """A tool call the framework queued for human approval."""

    call_id: str
    name: str
    arguments: str
    request: Content


@dataclass
class TurnOutcome:
    """Result of a single agent turn."""

    text: str = ""
    pending_approval: PendingApproval | None = None


def extract_approval_request(content: Content) -> PendingApproval | None:
    """Build a :class:`PendingApproval` from ``function_approval_request`` content."""
    if getattr(content, "type", None) != "function_approval_request":
        return None
    function_call = getattr(content, "function_call", None)
    call_id = getattr(content, "call_id", "") or getattr(function_call, "call_id", "") or ""
    name = getattr(function_call, "name", "") or getattr(content, "name", "") or ""
    arguments = getattr(function_call, "arguments", "") or ""
    return PendingApproval(call_id=str(call_id), name=str(name), arguments=str(arguments), request=content)


def dispatch_update(
    update: Any,
    emit: Callable[[AgentEvent], None],
    thinking_parts_out: list[str] | None,
) -> PendingApproval | None:
    """Translate one ``AgentResponseUpdate`` into our fine-grained events.

    Returns a :class:`PendingApproval` when the update carries an approval request.
    """
    pending: PendingApproval | None = None

    for content in getattr(update, "contents", None) or []:
        ctype = getattr(content, "type", None)

        if ctype == "text":
            text = getattr(content, "text", "") or ""
            if text:
                emit(TextDeltaEvent(delta=text))

        elif ctype in _THINKING_CONTENT_TYPES:
            thinking = (
                getattr(content, "text", "")
                or getattr(content, "thinking", "")
                or getattr(content, "reasoning_content", "")
                or ""
            )
            if thinking:
                if thinking_parts_out is not None:
                    thinking_parts_out.append(str(thinking))
                emit(ThinkingDeltaEvent(delta=str(thinking)))

        elif ctype == "usage":
            details = getattr(content, "usage_details", None) or {}
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

        elif ctype == "function_approval_request":
            pending = extract_approval_request(content)

    if pending is None:
        _extract_raw_thinking(getattr(update, "raw_representation", None), emit, thinking_parts_out)

    return pending


def _extract_raw_thinking(
    raw: Any,
    emit: Callable[[AgentEvent], None],
    thinking_parts_out: list[str] | None,
) -> None:
    """Fallback: pull reasoning out of provider-specific raw payloads.

    Most providers are normalised onto native content types (handled by
    :func:`dispatch_update`); this covers providers that only expose reasoning on
    the raw chunk, such as Anthropic's ``content_block_delta``.
    """
    if raw is None:
        return

    nested = getattr(raw, "raw_representation", None)
    if nested is not None and nested is not raw:
        raw = nested

    candidates: list[Any] = []

    if isinstance(raw, dict):
        for choice in raw.get("choices", []) or []:
            if isinstance(choice, dict):
                delta = choice.get("delta") or {}
                if isinstance(delta, dict) and delta.get("reasoning_content"):
                    candidates.append(delta["reasoning_content"])
        if raw.get("type") == "thinking" and raw.get("text"):
            candidates.append(raw["text"])
    else:
        for choice in getattr(raw, "choices", None) or []:
            delta = getattr(choice, "delta", None)
            reasoning = getattr(delta, "reasoning_content", None) if delta is not None else None
            if reasoning:
                candidates.append(reasoning)

        if getattr(raw, "type", None) == "content_block_delta":
            delta = getattr(raw, "delta", None)
            d_type = delta.get("type") if isinstance(delta, dict) else getattr(delta, "type", None)
            if d_type == "thinking":
                thinking = delta.get("thinking") if isinstance(delta, dict) else getattr(delta, "thinking", None)
                if thinking:
                    candidates.append(thinking)
        elif getattr(raw, "type", None) == "thinking":
            text = getattr(raw, "text", None)
            if text:
                candidates.append(text)

    for value in candidates:
        text = str(value)
        if not text:
            continue
        if thinking_parts_out is not None:
            thinking_parts_out.append(text)
        emit(ThinkingDeltaEvent(delta=text))


def _messages_from_session(session: AgentSession) -> list[Message]:
    """Read the conversation transcript the framework session is holding."""
    state = (session.to_dict() or {}).get("state") or {}
    raw: Any = None
    entry = state.get("in_memory")
    if isinstance(entry, dict) and "messages" in entry:
        raw = entry["messages"]
    elif isinstance(state.get("messages"), list):
        raw = state["messages"]
    if not isinstance(raw, list):
        return []

    messages: list[Message] = []
    for item in raw:
        if isinstance(item, Message):
            messages.append(item)
        elif isinstance(item, dict):
            try:
                messages.append(Message.from_dict(item))
            except Exception:
                role = item.get("role", "user")
                messages.append(Message(role=role, contents=[]))
    return messages


def _synthesize_text(messages: list[Message]) -> str:
    """Combine assistant text contents into a final user-facing string."""
    parts: list[str] = []
    for msg in messages:
        if getattr(msg, "role", None) != "assistant":
            continue
        for content in getattr(msg, "contents", None) or []:
            if getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    parts.append(text)
    return "".join(parts)


class AgentRuntime:
    """Owns one harness agent plus its framework session for a xiaoqiao session."""

    def __init__(
        self,
        *,
        client: Any,
        tools: list[Any],
        session: AgentSession,
        instructions: str,
        on_event: Callable[[AgentEvent], None],
        settings: Settings | None = None,
        thinking_level: str | None = None,
        skill_provider: Any | None = None,
        mcp_tools: list[Any] | None = None,
    ) -> None:
        self._session = session
        self._pending: dict[str, PendingApproval] = {}

        tool_list = [*tools, *(mcp_tools or [])]

        # Compaction needs BOTH bounds: the harness only builds its default
        # ContextWindowCompactionStrategy when max_context_window_tokens and
        # max_output_tokens are both present, and silently disables compaction
        # otherwise (see `_assemble_compaction`).
        max_context: int | None = None
        max_output: int | None = None
        if settings is not None:
            from xiaoqiao.settings import model_config

            cfg = model_config(settings, getattr(session, "model", None) or None)
            if cfg is not None:
                context_window = cfg.max_context_size
                max_tokens = cfg.max_output_size
                if isinstance(context_window, int) and context_window > 0:
                    max_context = context_window
                    # Keep the output bound strictly below the window, as the
                    # harness rejects max_output_tokens >= max_context_window_tokens.
                    if isinstance(max_tokens, int) and 0 < max_tokens < context_window:
                        max_output = max_tokens
                    else:
                        max_output = max(context_window // 8, 1)

        # Tool lifecycle events (tool_call_start / tool_execution_start / _end) are
        # not visible in the response stream, so keep our FunctionMiddleware for them.
        # The harness merges this into its own chain rather than replacing it.
        from xiaoqiao.tool_events import ToolEventMiddleware

        self._tool_middleware = ToolEventMiddleware(on_event)

        kwargs: dict[str, Any] = {
            "client": client,
            "name": "Xiaoqiao",
            "description": "Xiaoqiao harness runtime.",
            "agent_instructions": instructions,
            "tools": tool_list,
            "skills_provider": skill_provider,
            "middleware": [self._tool_middleware],
            # The framework session owns the conversation, so our own transcript
            # is a display copy rather than a second source of truth.
            "mode_provider": AgentModeProvider(default_mode="execute"),
        }
        if max_context is not None and max_output is not None:
            kwargs["max_context_window_tokens"] = max_context
            kwargs["max_output_tokens"] = max_output

        self._agent: Agent = create_harness_agent(**kwargs)
        self._compaction_bounds = (max_context, max_output)

        self._thinking_level = thinking_level

    @property
    def agent(self) -> Agent:
        return self._agent

    @property
    def agent_session(self) -> AgentSession:
        """The framework session holding the conversation state."""
        return self._session

    @property
    def transcript(self) -> list[Message]:
        """Conversation so far, as held by the framework session."""
        return _messages_from_session(self._session)

    def close(self) -> None:
        self._pending.clear()

    def _run_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self._thinking_level:
            from xiaoqiao.thinking import thinking_options_for_level

            options.update(thinking_options_for_level(self._thinking_level))
        return options

    async def _stream(
        self,
        inputs: Any,
        emit: Callable[[AgentEvent], None],
    ) -> tuple[PendingApproval | None, str]:
        """Stream one run, translating updates into events.

        Returns ``(pending_approval, text)`` where *text* covers only the messages
        produced by this run (the transcript also holds earlier turns).
        """
        from agent_framework._types import ChatOptions

        # The tool middleware may outlive a single emit callback, so keep it pointed
        # at the caller's sink for the duration of this run.
        self._tool_middleware.set_emit(emit)

        before = len(self.transcript)
        stream = self._agent.run(
            inputs,
            stream=True,
            session=self._session,
            options=cast("ChatOptions", self._run_options()),
        )
        pending: PendingApproval | None = None
        async for update in stream:
            found = dispatch_update(update, emit, None)
            if found is not None:
                pending = found
        await stream.get_final_response()

        self._tool_middleware.set_emit(lambda _event: None)

        if pending is not None:
            emit(
                ToolApprovalRequestEvent(
                    call_id=pending.call_id,
                    name=pending.name,
                    arguments=pending.arguments,
                )
            )

        return pending, _synthesize_text(self.transcript[before:])

    async def run_turn(self, text: str, emit: Callable[[AgentEvent], None]) -> TurnOutcome:
        """Run one user turn through the harness agent."""
        pending, turn_text = await self._stream(text, emit)
        if pending is not None:
            self._pending[pending.call_id] = pending
            return TurnOutcome(pending_approval=pending)

        emit(TurnEndEvent(reason="complete"))
        emit(DoneEvent())
        return TurnOutcome(text=turn_text)

    async def resolve_approval(
        self,
        call_id: str,
        approved: bool,
        emit: Callable[[AgentEvent], None],
    ) -> TurnOutcome:
        """Resume a paused turn with the human's approval decision."""
        pending = self._pending.pop(call_id, None)
        if pending is None:
            logger.warning("No pending approval for call_id=%s", call_id)
            emit(DoneEvent())
            return TurnOutcome()

        response = pending.request.to_function_approval_response(approved=approved)
        message = Message(role="user", contents=[response])

        found, turn_text = await self._stream([message], emit)
        if found is not None:
            self._pending[found.call_id] = found
            return TurnOutcome(pending_approval=found)

        emit(TurnEndEvent(reason="complete"))
        emit(DoneEvent())
        return TurnOutcome(text=turn_text)
