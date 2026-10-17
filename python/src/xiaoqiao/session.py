"""Session persistence for 小巧.

Saves conversation history as JSONL files (one JSON object per message line).
A session index file tracks available sessions.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xiaoqiao.paths import config_dir

logger = logging.getLogger(__name__)


# ── Data types ──────────────────────────────────────────────────


@dataclass
class SessionInfo:
    """Metadata about a saved session."""

    id: str
    created_at: str
    updated_at: str
    message_count: int
    title: str = ""
    model: str = ""
    model_provider: str = ""
    workspace: str = ""
    bot_id: str = ""
    status: str = "idle"
    session_file: str = ""
    session_started_at: str = ""
    last_interaction_at: str = ""
    started_at: str = ""
    ended_at: str = ""
    runtime_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class SessionData:
    """A serialisable session containing messages and metadata."""

    id: str
    messages: list[dict] = field(default_factory=list)
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    model: str = ""
    model_provider: str = ""
    workspace: str = ""
    bot_id: str = ""
    status: str = "idle"
    session_file: str = ""
    session_started_at: str = ""
    last_interaction_at: str = ""
    started_at: str = ""
    ended_at: str = ""
    runtime_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float = 0.0


# ── Session store ───────────────────────────────────────────────


_SESSIONS_DIR = config_dir() / "sessions"
_INDEX_FILE = "sessions.json"


def _session_dir() -> Path:
    return _SESSIONS_DIR


def _session_path(session_id: str) -> Path:
    return _session_dir() / f"{session_id}.jsonl"


def _index_path() -> Path:
    return _session_dir() / _INDEX_FILE


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_index() -> dict[str, SessionInfo]:
    """Load the session index from disk."""
    path = _index_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            sid: SessionInfo(
                id=info.get("id", sid),
                created_at=info.get("created_at", ""),
                updated_at=info.get("updated_at", ""),
                message_count=info.get("message_count", 0),
                title=info.get("title", ""),
                model=info.get("model", ""),
                model_provider=info.get("model_provider", ""),
                workspace=info.get("workspace", ""),
                bot_id=info.get("bot_id", ""),
                status=info.get("status", "idle"),
                session_file=info.get("session_file", ""),
                session_started_at=info.get("session_started_at", ""),
                last_interaction_at=info.get("last_interaction_at", ""),
                started_at=info.get("started_at", ""),
                ended_at=info.get("ended_at", ""),
                runtime_ms=info.get("runtime_ms", 0),
                input_tokens=info.get("input_tokens", 0),
                output_tokens=info.get("output_tokens", 0),
                total_tokens=info.get("total_tokens", 0),
                cache_read_tokens=info.get("cache_read_tokens", 0),
                reasoning_tokens=info.get("reasoning_tokens", 0),
                estimated_cost_usd=info.get("estimated_cost_usd", 0.0),
            )
            for sid, info in data.items()
        }
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Failed to load session index: %s", exc)
        return {}


def _info_to_dict(info: SessionInfo) -> dict[str, Any]:
    return {
        "id": info.id,
        "created_at": info.created_at,
        "updated_at": info.updated_at,
        "message_count": info.message_count,
        "title": info.title,
        "model": info.model,
        "model_provider": info.model_provider,
        "workspace": info.workspace,
        "bot_id": info.bot_id,
        "status": info.status,
        "session_file": info.session_file,
        "session_started_at": info.session_started_at,
        "last_interaction_at": info.last_interaction_at,
        "started_at": info.started_at,
        "ended_at": info.ended_at,
        "runtime_ms": info.runtime_ms,
        "input_tokens": info.input_tokens,
        "output_tokens": info.output_tokens,
        "total_tokens": info.total_tokens,
        "cache_read_tokens": info.cache_read_tokens,
        "reasoning_tokens": info.reasoning_tokens,
        "estimated_cost_usd": info.estimated_cost_usd,
    }


def _save_index(index: dict[str, SessionInfo]) -> None:
    """Save the session index to disk."""
    _session_dir().mkdir(parents=True, exist_ok=True)
    data = {sid: _info_to_dict(info) for sid, info in index.items()}
    _index_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_sessions() -> list[SessionInfo]:
    """Return all saved sessions, newest first."""
    index = _load_index()
    sessions = sorted(index.values(), key=lambda s: s.updated_at, reverse=True)
    return sessions


def create_session(
    title: str = "",
    model: str = "",
    workspace: str = "",
    bot_id: str = "",
) -> SessionData:
    """Create a new empty session."""
    now = _now()
    session_id = uuid.uuid4().hex[:12]
    provider_id, _ = _split_model(model) if model else ("", "")
    return SessionData(
        id=session_id,
        title=title,
        model=model,
        model_provider=provider_id,
        workspace=workspace,
        bot_id=bot_id,
        created_at=now,
        updated_at=now,
        session_file=str(_session_path(session_id)),
        session_started_at=now,
    )


def _split_model(value: str) -> tuple[str, str]:
    if "/" in value:
        provider, model = value.split("/", 1)
        return provider, model
    return "", value


def _aggregate_usage(messages: list[dict]) -> dict[str, int]:
    """Sum usage_details from all 'usage' content blocks in messages."""
    total: dict[str, int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "reasoning_tokens": 0,
    }
    for msg in messages:
        for c in msg.get("contents", []):
            if c.get("type") != "usage":
                continue
            details = c.get("usage_details") or {}
            total["input_tokens"] += details.get("input_token_count", 0) or 0
            total["output_tokens"] += details.get("output_token_count", 0) or 0
            total["total_tokens"] += details.get("total_token_count", 0) or 0
            total["cache_read_tokens"] += details.get("cache_read_input_token_count", 0) or 0
            total["reasoning_tokens"] += details.get("reasoning_output_token_count", 0) or 0
    return total


def save_session(session: SessionData) -> None:
    """Save a session's messages to disk and update the index."""
    _session_dir().mkdir(parents=True, exist_ok=True)
    path = _session_path(session.id)

    # Write messages as JSONL
    with path.open("w", encoding="utf-8") as f:
        for msg in session.messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    # Update index
    session.updated_at = _now()
    session.last_interaction_at = session.updated_at
    usage = _aggregate_usage(session.messages)
    index = _load_index()
    existing = index.get(session.id)
    session_started_at = session.session_started_at or (existing.session_started_at if existing else session.created_at)
    index[session.id] = SessionInfo(
        id=session.id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=len(session.messages),
        title=session.title,
        model=session.model,
        model_provider=session.model_provider,
        workspace=session.workspace,
        bot_id=session.bot_id,
        status=session.status,
        session_file=session.session_file or str(path),
        session_started_at=session_started_at,
        last_interaction_at=session.last_interaction_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        runtime_ms=session.runtime_ms,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        total_tokens=usage["total_tokens"],
        cache_read_tokens=usage["cache_read_tokens"],
        reasoning_tokens=usage["reasoning_tokens"],
        estimated_cost_usd=session.estimated_cost_usd,
    )
    _save_index(index)


def load_session(session_id: str) -> SessionData | None:
    """Load a session from disk by ID."""
    path = _session_path(session_id)
    if not path.exists():
        return None

    index = _load_index()
    info = index.get(session_id)
    if info is None:
        return None

    messages: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return SessionData(
        id=session_id,
        messages=messages,
        title=info.title,
        model=info.model,
        model_provider=info.model_provider,
        workspace=info.workspace,
        bot_id=info.bot_id,
        status=info.status,
        session_file=info.session_file or str(path),
        session_started_at=info.session_started_at,
        last_interaction_at=info.last_interaction_at,
        started_at=info.started_at,
        ended_at=info.ended_at,
        runtime_ms=info.runtime_ms,
        input_tokens=info.input_tokens,
        output_tokens=info.output_tokens,
        total_tokens=info.total_tokens,
        cache_read_tokens=info.cache_read_tokens,
        reasoning_tokens=info.reasoning_tokens,
        estimated_cost_usd=info.estimated_cost_usd,
        created_at=info.created_at,
        updated_at=info.updated_at,
    )


def update_session(
    session_id: str,
    title: str | None = None,
    model: str | None = None,
    bot_id: str | None = None,
) -> SessionData | None:
    """Update a session's title, model and/or owning bot."""
    index = _load_index()
    info = index.get(session_id)
    if info is None:
        return None
    if title is not None:
        info.title = title
        info.updated_at = _now()
    if model is not None:
        info.model = model
        info.model_provider = _split_model(model)[0]
        info.updated_at = _now()
    if bot_id is not None:
        info.bot_id = bot_id
        info.updated_at = _now()
    _save_index(index)

    session = load_session(session_id)
    if session is None:
        return None
    if title is not None:
        session.title = title
    if model is not None:
        session.model = model
        session.model_provider = _split_model(model)[0]
    return session


def start_session_run(session_id: str) -> SessionData | None:
    """Mark a session as running and record start time."""
    index = _load_index()
    info = index.get(session_id)
    if info is None:
        return None
    now = _now()
    info.status = "running"
    info.started_at = now
    info.ended_at = ""
    info.runtime_ms = 0
    info.updated_at = now
    _save_index(index)

    session = load_session(session_id)
    if session is None:
        return None
    session.status = "running"
    session.started_at = now
    session.ended_at = ""
    session.runtime_ms = 0
    return session


def end_session_run(session_id: str, error: bool = False) -> SessionData | None:
    """Mark a session as done/error and record runtime."""
    index = _load_index()
    info = index.get(session_id)
    if info is None:
        return None
    now = _now()
    info.status = "error" if error else "done"
    info.ended_at = now
    if info.started_at:
        try:
            start = datetime.fromisoformat(info.started_at)
            end = datetime.fromisoformat(now)
            info.runtime_ms = int((end - start).total_seconds() * 1000)
        except ValueError:
            info.runtime_ms = 0
    info.updated_at = now
    _save_index(index)

    session = load_session(session_id)
    if session is None:
        return None
    session.status = info.status
    session.ended_at = now
    session.runtime_ms = info.runtime_ms
    return session


def delete_session(session_id: str) -> bool:
    """Delete a session by ID. Returns True if deleted."""
    path = _session_path(session_id)
    if not path.exists():
        return False
    path.unlink()
    index = _load_index()
    index.pop(session_id, None)
    _save_index(index)
    return True


# ── Serialisation helpers ───────────────────────────────────────


def message_to_dict(msg: object) -> dict:
    """Convert an agent-framework Message to a JSON-serialisable dict."""
    contents = []
    usage_details: dict[str, Any] | None = None
    thinking_parts: list[str] = []
    for c in getattr(msg, "contents", None) or []:
        ctype = getattr(c, "type", None)
        # Thinking/reasoning content blocks are not replayed to the model API
        # on subsequent turns, but their text must still be persisted so the
        # TUI / debugging tools can display what the model reasoned about.
        if ctype in ("thinking", "reasoning", "text_reasoning"):
            ctext = (
                getattr(c, "text", None) or getattr(c, "thinking", None) or getattr(c, "reasoning_content", None) or ""
            )
            if ctext:
                thinking_parts.append(str(ctext))
            continue
        if ctype == "usage":
            # Preserve the full usage_details dict as returned by the API.
            usage_details = getattr(c, "usage_details", None)
            contents.append({"type": "usage", "usage_details": usage_details})
            continue
        entry = {"type": ctype}
        if ctype == "text":
            entry["text"] = c.text
        elif ctype == "function_call":
            entry["call_id"] = c.call_id
            entry["name"] = c.name
            entry["arguments"] = c.arguments
        elif ctype == "function_result":
            entry["call_id"] = c.call_id
            entry["name"] = c.name
            entry["result"] = c.result
        contents.append(entry)
    result: dict[str, Any] = {"role": getattr(msg, "role", "user"), "contents": contents}
    # Merge thinking from additional_properties (legacy path set by loop.py)
    # with any thinking collected from content blocks above.
    additional_thinking = getattr(msg, "additional_properties", {}).get("thinking")
    if additional_thinking:
        thinking_parts.insert(0, str(additional_thinking))
    if thinking_parts:
        result["thinking"] = "\n".join(p for p in thinking_parts if p)
    # Also expose usage at the message top level for openclaw-style readers.
    if usage_details:
        result["usage"] = usage_details
    return result


def dict_to_message(d: dict) -> object:
    """Reconstruct an agent-framework Message from a dict."""
    from agent_framework._types import Content, Message

    contents = []
    for c in d.get("contents", []):
        t = c.get("type", "text")
        if t == "text":
            contents.append(Content(type="text", text=c.get("text", "")))
        elif t == "function_call":
            contents.append(
                Content(
                    type="function_call",
                    call_id=c.get("call_id", ""),
                    name=c.get("name", ""),
                    arguments=c.get("arguments", ""),
                )
            )
        elif t == "function_result":
            contents.append(
                Content(
                    type="function_result",
                    call_id=c.get("call_id", ""),
                    name=c.get("name", ""),
                    result=c.get("result", ""),
                )
            )
        elif t == "usage":
            # Usage blocks are kept in storage for accounting but are not
            # replayed to the model API on subsequent turns.
            continue
    additional_properties = {}
    thinking = d.get("thinking")
    if thinking:
        additional_properties["thinking"] = thinking
    return Message(
        role=d.get("role", "user"),
        contents=contents,
        additional_properties=additional_properties if additional_properties else None,
    )
