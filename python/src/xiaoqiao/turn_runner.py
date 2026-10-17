"""Session-scoped turn orchestration shared by both gateways.

The WebSocket and stdio gateways used to carry near-identical copies of this
logic (resolve session → build prompt → run the agent → persist → handle a
pending approval).  Keeping it here means one implementation to reason about.

What lives where:

* :class:`~xiaoqiao.agent_runtime.AgentRuntime` — owns the harness agent and
  the framework session, and translates framework stream updates into our events.
* :class:`TurnRunner` (this module) — the xiaoqiao session lifecycle around
  it: which session, which system prompt, and what gets persisted.

The framework session is the authoritative conversation state, because it owns
the ``tool_call`` / ``tool_result`` pairing that OpenAI-compatible APIs require.
The JSONL transcript is a projection of it, kept for history and the UI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from xiaoqiao.agent_runtime import AgentRuntime, PendingApproval

if TYPE_CHECKING:
    from xiaoqiao.events import AgentEvent
    from xiaoqiao.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """Outcome of one orchestrated turn."""

    text: str = ""
    pending_approval: PendingApproval | None = None


class TurnRunner:
    """Runs agent turns for xiaoqiao sessions, owning runtime lifetime.

    A runtime is cached per session id: the framework session inside it is the
    conversation state, so rebuilding it per turn would lose context — and
    rebuilding it between an approval request and its response would lose the
    pending tool call.
    """

    def __init__(
        self,
        *,
        tools: list[Any],
        settings: Settings | None,
        skill_provider: Any | None = None,
        mcp_tools: list[Any] | None = None,
    ) -> None:
        self._tools = tools or []
        self._settings = settings
        self._skill_provider = skill_provider
        self._mcp_tools = mcp_tools or []
        self._runtimes: dict[str, AgentRuntime] = {}

    # ── runtime lifetime ───────────────────────────────────────────

    def runtime_for(
        self,
        *,
        session_id: str,
        model: str,
        instructions: str,
        thinking_level: str | None,
        client: Any,
        on_event: Callable[[AgentEvent], None],
        tools: list[Any] | None = None,
    ) -> AgentRuntime:
        """Return the cached runtime for a session, creating it on first use."""
        cached = self._runtimes.get(session_id)
        if cached is not None:
            return cached

        from xiaoqiao.framework_session import get_or_create_framework_session

        runtime = AgentRuntime(
            client=client,
            tools=list(tools) if tools is not None else self._tools,
            session=get_or_create_framework_session(session_id),
            instructions=instructions,
            on_event=on_event,
            settings=self._settings,
            thinking_level=thinking_level,
            skill_provider=self._skill_provider,
            mcp_tools=self._mcp_tools,
        )
        self._runtimes[session_id] = runtime
        return runtime

    def remember(self, session: Any, runtime: AgentRuntime) -> None:
        """Persist the transcript (display) and the framework session (model state)."""
        from xiaoqiao.framework_session import save_framework_session
        from xiaoqiao.session import message_to_dict

        session.messages = [message_to_dict(m) for m in runtime.transcript]
        save_framework_session(runtime.agent_session)
