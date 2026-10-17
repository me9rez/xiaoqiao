"""Fine-grained agent events emitted by the custom loop to the gateway.

These are the events the TUI consumes to render real-time agent state.
Each maps to a JSON-RPC event emitted from the gateway to the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ── Fine-grained streaming events ──────────────────────────────────


@dataclass
class ThinkingDeltaEvent:
    """A reasoning/thinking token emitted by the model (e.g. Anthropic)."""

    type: Literal["thinking_delta"] = "thinking_delta"
    delta: str = ""


@dataclass
class TextDeltaEvent:
    """A visible text token emitted by the model."""

    type: Literal["text_delta"] = "text_delta"
    delta: str = ""


@dataclass
class ToolCallStartEvent:
    """The LLM has initiated a tool call (all args known)."""

    type: Literal["tool_call_start"] = "tool_call_start"
    call_id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class ToolExecutionStartEvent:
    """A tool call begins execution."""

    type: Literal["tool_execution_start"] = "tool_execution_start"
    call_id: str = ""
    name: str = ""


@dataclass
class ToolExecutionDeltaEvent:
    """Incremental output from a running tool (e.g. stdout lines)."""

    type: Literal["tool_execution_delta"] = "tool_execution_delta"
    call_id: str = ""
    line: str = ""


@dataclass
class ToolExecutionEndEvent:
    """A tool call has finished execution."""

    type: Literal["tool_execution_end"] = "tool_execution_end"
    call_id: str = ""
    name: str = ""
    result: str = ""
    ok: bool = True
    exit_code: int | None = None
    error: str | None = None


# ── Turn / session lifecycle events ────────────────────────────────


@dataclass
class TurnEndEvent:
    """One agent turn completed (LLM call + optional tool round)."""

    type: Literal["turn_end"] = "turn_end"
    reason: str = ""  # "complete" | "tool_calls" | "error"


@dataclass
class DoneEvent:
    """The entire agent run is finished."""

    type: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    """An unrecoverable error occurred during the agent run."""

    type: Literal["error"] = "error"
    message: str = ""
    recoverable: bool = False


@dataclass
class UsageEvent:
    """Token usage details returned by the LLM API for one turn."""

    type: Literal["usage"] = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    reasoning_tokens: int = 0
    details: dict[str, Any] = field(default_factory=dict)


# ── Human-in-the-loop approval events ──────────────────────────────


@dataclass
class ToolApprovalRequestEvent:
    """A tool call is waiting for human approval before execution."""

    type: Literal["tool_approval_request"] = "tool_approval_request"
    call_id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class ToolApprovalResponseEvent:
    """A human approval/rejection decision for a pending tool call."""

    type: Literal["tool_approval_response"] = "tool_approval_response"
    call_id: str = ""
    approved: bool = False
    reason: str = ""


# ── Union type for all events ──────────────────────────────────────


AgentEvent = (
    ThinkingDeltaEvent
    | TextDeltaEvent
    | ToolCallStartEvent
    | ToolExecutionStartEvent
    | ToolExecutionDeltaEvent
    | ToolExecutionEndEvent
    | TurnEndEvent
    | DoneEvent
    | ErrorEvent
    | UsageEvent
    | ToolApprovalRequestEvent
    | ToolApprovalResponseEvent
)
