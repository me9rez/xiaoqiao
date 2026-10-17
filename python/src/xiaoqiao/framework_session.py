"""Bridge xiaoqiao sessions to agent-framework AgentSession objects.

This module creates, persists, and restores the framework-side session used by
ToolApprovalMiddleware and workflow checkpointing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent_framework import AgentSession

from xiaoqiao.session import _session_dir

logger = logging.getLogger(__name__)


def _framework_session_path(session_id: str) -> Path:
    """Return the filesystem path for a serialized AgentSession."""
    return _session_dir() / f"{session_id}.framework_session.json"


def create_framework_session(session_id: str) -> AgentSession:
    """Create a fresh framework session bound to a xiaoqiao session id."""
    return AgentSession(session_id=session_id)


def load_framework_session(session_id: str) -> AgentSession | None:
    """Restore a previously saved framework session, or return None."""
    path = _framework_session_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentSession.from_dict(data)
    except Exception:
        logger.exception("Failed to load framework session %s", session_id)
        return None


def save_framework_session(session: AgentSession) -> None:
    """Persist an AgentSession to disk."""
    path = _framework_session_path(session.session_id)
    _session_dir().mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def get_or_create_framework_session(session_id: str) -> AgentSession:
    """Load an existing framework session or create a new one."""
    return load_framework_session(session_id) or create_framework_session(session_id)


def delete_framework_session(session_id: str) -> None:
    """Remove the persisted framework session for a xiaoqiao session."""
    path = _framework_session_path(session_id)
    if path.exists():
        path.unlink()


def serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Serialize a list of Message-like objects to plain dicts."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        if hasattr(msg, "to_dict"):
            result.append(msg.to_dict())
        else:
            result.append(dict(msg))
    return result
