"""WebSocket gateway server — replaces stdin/stdout transport.

Usage:
    python -m coding_agent.main --ws-port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve

from coding_agent.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolApprovalRequestEvent,
    ToolApprovalResponseEvent,
    ToolCallStartEvent,
    ToolExecutionDeltaEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
    UsageEvent,
)
from coding_agent.framework_session import (
    get_or_create_framework_session,
    save_framework_session,
)
from coding_agent.mcp import (
    get_connector,
    install_connector,
    list_connectors,
    uninstall_connector,
    update_connector_config,
)
from coding_agent.session import (
    create_session,
    delete_session,
    end_session_run,
    list_sessions,
    load_session,
    message_to_dict,
    save_session,
    start_session_run,
    update_session,
)
from coding_agent.settings import Settings, _split_selected_model, build_client, model_config, thinking_level
from coding_agent.settings import load as load_settings
from coding_agent.settings import save as save_settings
from coding_agent.skills import (
    get_skill,
    get_skill_file_content,
    get_skill_files,
    install_skill,
    list_skills,
    toggle_skill,
    uninstall_skill,
    update_skill,
)
from coding_agent.thinking import thinking_options_for_model
from coding_agent.workflow_loop import PendingApproval, WorkflowOutput

logger = logging.getLogger(__name__)


def _session_info_to_dict(info: Any) -> dict[str, Any]:
    return {
        "id": info.id,
        "createdAt": info.created_at,
        "updatedAt": info.updated_at,
        "messageCount": info.message_count,
        "title": info.title,
        "model": info.model,
        "modelProvider": info.model_provider,
        "workspace": info.workspace,
        "status": info.status,
        "sessionStartedAt": info.session_started_at,
        "lastInteractionAt": info.last_interaction_at,
        "startedAt": info.started_at,
        "endedAt": info.ended_at,
        "runtimeMs": info.runtime_ms,
        "inputTokens": info.input_tokens,
        "outputTokens": info.output_tokens,
        "totalTokens": info.total_tokens,
        "cacheReadTokens": info.cache_read_tokens,
        "reasoningTokens": info.reasoning_tokens,
        "estimatedCostUsd": info.estimated_cost_usd,
    }


def _session_data_to_dict(session: Any) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "model": session.model,
        "modelProvider": session.model_provider,
        "workspace": session.workspace,
        "createdAt": session.created_at,
        "updatedAt": session.updated_at,
        "messages": session.messages,
        "status": session.status,
        "sessionStartedAt": session.session_started_at,
        "lastInteractionAt": session.last_interaction_at,
        "startedAt": session.started_at,
        "endedAt": session.ended_at,
        "runtimeMs": session.runtime_ms,
        "inputTokens": session.input_tokens,
        "outputTokens": session.output_tokens,
        "totalTokens": session.total_tokens,
        "cacheReadTokens": session.cache_read_tokens,
        "reasoningTokens": session.reasoning_tokens,
        "estimatedCostUsd": session.estimated_cost_usd,
    }


def _serialize_event(event: AgentEvent) -> dict[str, Any]:
    match event:
        case ThinkingDeltaEvent(delta=d):
            return {"type": "thinking_delta", "delta": d}
        case TextDeltaEvent(delta=d):
            return {"type": "text_delta", "delta": d}
        case ToolCallStartEvent(call_id=rid, name=n, arguments=a):
            return {"type": "tool_call_start", "callId": rid, "name": n, "arguments": a}
        case ToolExecutionStartEvent(call_id=rid, name=n):
            return {"type": "tool_execution_start", "callId": rid, "name": n}
        case ToolExecutionDeltaEvent(call_id=rid, line=l):
            return {"type": "tool_execution_delta", "callId": rid, "line": l}
        case ToolExecutionEndEvent(call_id=rid, name=n, ok=ok, exit_code=ec, error=err, result=r):
            return {
                "type": "tool_execution_end",
                "callId": rid,
                "name": n,
                "ok": ok,
                "exitCode": ec,
                "error": err,
                "result": r,
            }
        case TurnEndEvent(reason=r):
            return {"type": "turn_end", "reason": r}
        case UsageEvent(
            input_tokens=i,
            output_tokens=o,
            total_tokens=t,
            cache_read_tokens=c,
            reasoning_tokens=r,
            details=d,
        ):
            return {
                "type": "usage",
                "inputTokens": i,
                "outputTokens": o,
                "totalTokens": t,
                "cacheReadTokens": c,
                "reasoningTokens": r,
                "details": d,
            }
        case DoneEvent():
            return {"type": "done"}
        case ErrorEvent(message=m, recoverable=r):
            return {"type": "error", "message": m, "recoverable": r}
        case ToolApprovalRequestEvent(call_id=rid, name=n, arguments=a):
            return {"type": "tool_approval_request", "callId": rid, "name": n, "arguments": a}
        case ToolApprovalResponseEvent(call_id=rid, approved=ap):
            return {"type": "tool_approval_response", "callId": rid, "approved": ap}
    return {"type": "unknown", "raw": str(event)}


def _summarize_event(obj: dict[str, Any]) -> str:
    """Return a one-line summary of key fields for logging."""
    t = obj.get("type", "")
    parts: list[str] = []
    if call_id := obj.get("callId"):
        parts.append(f"id={call_id}")
    if name := obj.get("name"):
        parts.append(f"name={name}")
    if t == "tool_call_start":
        args = obj.get("arguments", "")[:80]
        parts.append(f"args={args}")
    elif t == "tool_execution_end":
        ok = obj.get("ok", "?")
        ec = obj.get("exitCode")
        err = obj.get("error")
        r = obj.get("result", "")
        parts.append(f"ok={ok}")
        if ec is not None:
            parts.append(f"exit={ec}")
        if r:
            parts.append(f"result={len(r)}B")
        if err:
            parts.append(f"error={err[:100]}")
    elif t == "turn_end":
        parts.append(f"reason={obj.get('reason', '?')}")
    elif t == "error":
        parts.append(f"msg={obj.get('message', '?')[:120]}")
    return " ".join(parts)


class WsGatewayServer:
    """WebSocket gateway — one connection, dispatches to agent loop."""

    def __init__(
        self,
        tools: list[Any] | None = None,
        settings: Settings | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        skill_provider: Any | None = None,
        mcp_tools: list[Any] | None = None,
    ) -> None:
        self._tools = tools or []
        self._settings = settings
        self._host = host
        self._port = port
        self._skill_provider = skill_provider
        self._mcp_tools = mcp_tools or []
        self._current_tasks: dict[str, asyncio.Task[None]] = {}
        self._session: Any = None
        self._ws: ServerConnection | None = None
        self._emit_tasks: list[asyncio.Task[None]] = []
        self._clients: dict[str, Any] = {}
        self._connections: set[ServerConnection] = set()
        self._workspace = self._detect_workspace()
        self._pending_approvals: dict[str, Any] = {}

    def _client_for(self, model: str) -> Any:
        if self._settings is None:
            raise RuntimeError("Settings not available")
        if model not in self._clients:
            self._clients[model] = build_client(self._settings, model)
        return self._clients[model]

    def _detect_workspace(self) -> dict[str, str]:
        from coding_agent.system_prompt import discover_project_context

        ctx = discover_project_context()
        path = ctx.cwd or str(Path.cwd().resolve())
        return {"name": Path(path).name, "path": path}

    def _emit(self, event: AgentEvent, session_id: str = "") -> None:
        obj = _serialize_event(event)
        if session_id:
            obj["sessionId"] = session_id
        if obj.get("type") not in ("text_delta", "thinking_delta", "tool_execution_delta"):
            fields = _summarize_event(obj)
            print(f"→ {obj.get('type', '?')} {fields}", file=sys.stderr, flush=True)
        if not self._connections:
            return
        data = json.dumps(obj, ensure_ascii=False)
        for conn in list(self._connections):
            try:
                task = asyncio.create_task(conn.send(data))
                self._emit_tasks.append(task)
                task.add_done_callback(self._emit_tasks.remove)
            except Exception:
                self._connections.discard(conn)

    def _send_rpc_response(self, request_id: str, result: Any) -> None:
        if self._ws is None:
            return
        obj = {"type": "rpc_response", "id": request_id, "result": result}
        try:
            task = asyncio.create_task(self._ws.send(json.dumps(obj, ensure_ascii=False)))
            self._emit_tasks.append(task)
            task.add_done_callback(self._emit_tasks.remove)
        except Exception:
            pass

    def _send_rpc_error(self, request_id: str, message: str) -> None:
        if self._ws is None:
            return
        obj = {"type": "rpc_response", "id": request_id, "error": {"message": message}}
        try:
            task = asyncio.create_task(self._ws.send(json.dumps(obj, ensure_ascii=False)))
            self._emit_tasks.append(task)
            task.add_done_callback(self._emit_tasks.remove)
        except Exception:
            pass

    async def _handle_ws(self, ws: ServerConnection) -> None:
        self._ws = ws
        self._connections.add(ws)
        logger.info("Client connected from %s", ws.remote_address)
        try:
            await ws.send(json.dumps({"type": "ready", "workspace": self._workspace}))

            async for raw in ws:
                try:
                    request = json.loads(raw)
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON: %s", exc)
                    continue

                method = request.get("method")
                params = request.get("params", {})
                request_id = request.get("id")
                if method == "prompt":
                    text = params.get("text", "")
                    session_id = params.get("sessionId", "")
                    logger.info("← prompt (session=%s, text=%.80s)", session_id, text)
                    self._current_tasks[session_id] = asyncio.create_task(self._handle_prompt(text, session_id))
                elif method == "cancel":
                    session_id = params.get("sessionId", "")
                    if session_id and session_id in self._current_tasks:
                        task = self._current_tasks[session_id]
                        if not task.done():
                            task.cancel()
                elif method == "listSessions":
                    try:
                        sessions = list_sessions()
                        self._send_rpc_response(request_id, [_session_info_to_dict(s) for s in sessions])
                    except Exception as exc:
                        logger.exception("listSessions failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createSession":
                    try:
                        title = params.get("title", "")
                        model = params.get("model", "")
                        workspace = params.get("workspace", "")
                        session = create_session(title=title, model=model, workspace=workspace)
                        save_session(session)
                        self._send_rpc_response(request_id, _session_data_to_dict(session))
                    except Exception as exc:
                        logger.exception("createSession failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "loadSession":
                    try:
                        session_id = params.get("sessionId", "")
                        session = load_session(session_id)
                        if session is None:
                            self._send_rpc_error(request_id, f"Session not found: {session_id}")
                        else:
                            self._send_rpc_response(request_id, _session_data_to_dict(session))
                    except Exception as exc:
                        logger.exception("loadSession failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "deleteSession":
                    try:
                        session_id = params.get("sessionId", "")
                        ok = delete_session(session_id)
                        self._send_rpc_response(request_id, {"ok": ok})
                    except Exception as exc:
                        logger.exception("deleteSession failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateSession":
                    try:
                        session_id = params.get("sessionId", "")
                        title = params.get("title")
                        model = params.get("model")
                        session = update_session(session_id, title=title, model=model)
                        if session is None:
                            self._send_rpc_error(request_id, f"Session not found: {session_id}")
                        else:
                            self._send_rpc_response(request_id, _session_data_to_dict(session))
                    except Exception as exc:
                        logger.exception("updateSession failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "getSettings":
                    try:
                        s = load_settings()
                        self._send_rpc_response(
                            request_id,
                            {
                                "primaryModel": s.primary_model,
                                "providers": s.providers,
                                "max_turns": s.max_turns,
                            },
                        )
                    except Exception as exc:
                        logger.exception("getSettings failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateSettings":
                    try:
                        s = load_settings()
                        if "primaryModel" in params:
                            s.primary_model = params["primaryModel"]
                        if "selectedModel" in params:
                            s.primary_model = params["selectedModel"]
                        if "providers" in params:
                            s.providers = params["providers"]
                        if "max_turns" in params:
                            s.max_turns = params["max_turns"]
                        save_settings(s)
                        self._send_rpc_response(
                            request_id,
                            {
                                "primaryModel": s.primary_model,
                                "providers": s.providers,
                                "max_turns": s.max_turns,
                            },
                        )
                    except Exception as exc:
                        logger.exception("updateSettings failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "approval_response":
                    call_id = params.get("callId", "")
                    approved = bool(params.get("approved", False))
                    session_id = params.get("sessionId", "")
                    if call_id in self._pending_approvals:
                        task = asyncio.create_task(self._resume_approval(call_id, approved))
                        if session_id:
                            self._current_tasks[session_id] = task
                    else:
                        self._send_rpc_error(request_id, f"No pending approval: {call_id}")
                elif method == "listSkills":
                    try:
                        skills = list_skills()
                        self._send_rpc_response(request_id, {"skills": skills})
                    except Exception as exc:
                        logger.exception("listSkills failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "getSkill":
                    try:
                        name = params.get("name", "")
                        skill = get_skill(name)
                        if skill is None:
                            self._send_rpc_error(request_id, f"Skill not found: {name}")
                        else:
                            self._send_rpc_response(request_id, skill)
                    except Exception as exc:
                        logger.exception("getSkill failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "getSkillFiles":
                    try:
                        name = params.get("name", "")
                        files = get_skill_files(name)
                        if files is None:
                            self._send_rpc_error(request_id, f"Skill not found: {name}")
                        else:
                            self._send_rpc_response(request_id, {"files": files})
                    except Exception as exc:
                        logger.exception("getSkillFiles failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "getSkillFileContent":
                    try:
                        name = params.get("name", "")
                        filePath = params.get("filePath", "")
                        content = get_skill_file_content(name, filePath)
                        if content is None:
                            self._send_rpc_error(request_id, f"File not found: {filePath}")
                        else:
                            self._send_rpc_response(request_id, {"content": content})
                    except Exception as exc:
                        logger.exception("getSkillFileContent failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "installSkill":
                    try:
                        name = params.get("name", "")
                        source_dir = params.get("sourceDir")
                        skill = install_skill(name, source_dir)
                        self._send_rpc_response(request_id, {"success": True, "skill": skill})
                    except Exception as exc:
                        logger.exception("installSkill failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "uninstallSkill":
                    try:
                        name = params.get("name", "")
                        ok = uninstall_skill(name)
                        self._send_rpc_response(request_id, {"success": ok})
                    except Exception as exc:
                        logger.exception("uninstallSkill failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "toggleSkill":
                    try:
                        name = params.get("name", "")
                        enabled = params.get("enabled", True)
                        ok = toggle_skill(name, enabled)
                        self._send_rpc_response(request_id, {"success": ok})
                    except Exception as exc:
                        logger.exception("toggleSkill failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateSkill":
                    try:
                        name = params.get("name", "")
                        content = params.get("content", "")
                        ok = update_skill(name, content)
                        self._send_rpc_response(request_id, {"success": ok})
                    except Exception as exc:
                        logger.exception("updateSkill failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "listConnectors":
                    try:
                        connectors = list_connectors()
                        self._send_rpc_response(request_id, {"connectors": connectors})
                    except Exception as exc:
                        logger.exception("listConnectors failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "getConnector":
                    try:
                        name = params.get("name", "")
                        connector = get_connector(name)
                        if connector is None:
                            self._send_rpc_error(request_id, f"Connector not found: {name}")
                        else:
                            self._send_rpc_response(request_id, connector)
                    except Exception as exc:
                        logger.exception("getConnector failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "installConnector":
                    try:
                        name = params.get("name", "")
                        config = params.get("config")
                        ok = install_connector(name, config)
                        self._send_rpc_response(request_id, {"success": ok})
                    except Exception as exc:
                        logger.exception("installConnector failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "uninstallConnector":
                    try:
                        name = params.get("name", "")
                        ok = uninstall_connector(name)
                        self._send_rpc_response(request_id, {"success": ok})
                    except Exception as exc:
                        logger.exception("uninstallConnector failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateConnector":
                    try:
                        name = params.get("name", "")
                        config = params.get("config", {})
                        ok = update_connector_config(name, config)
                        self._send_rpc_response(request_id, {"success": ok})
                    except Exception as exc:
                        logger.exception("updateConnector failed")
                        self._send_rpc_error(request_id, str(exc))
                # --- Automation: Scheduled Tasks ---
                elif method == "listScheduledTasks":
                    try:
                        from coding_agent.automation import list_scheduled_tasks, task_to_dict

                        tasks = list_scheduled_tasks()
                        self._send_rpc_response(request_id, [task_to_dict(t) for t in tasks])
                    except Exception as exc:
                        logger.exception("listScheduledTasks failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createScheduledTask":
                    try:
                        from coding_agent.automation import create_scheduled_task, task_to_dict

                        task = create_scheduled_task(params)
                        self._send_rpc_response(request_id, task_to_dict(task))
                    except Exception as exc:
                        logger.exception("createScheduledTask failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateScheduledTask":
                    try:
                        from coding_agent.automation import task_to_dict, update_scheduled_task

                        task_id = params.get("id", "")
                        task = update_scheduled_task(task_id, params)
                        if task is None:
                            self._send_rpc_error(request_id, f"Task not found: {task_id}")
                        else:
                            self._send_rpc_response(request_id, task_to_dict(task))
                    except Exception as exc:
                        logger.exception("updateScheduledTask failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "deleteScheduledTask":
                    try:
                        from coding_agent.automation import delete_scheduled_task

                        task_id = params.get("id", "")
                        ok = delete_scheduled_task(task_id)
                        self._send_rpc_response(request_id, {"ok": ok})
                    except Exception as exc:
                        logger.exception("deleteScheduledTask failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "toggleScheduledTask":
                    try:
                        from coding_agent.automation import task_to_dict, toggle_scheduled_task

                        task_id = params.get("id", "")
                        enabled = params.get("enabled", True)
                        task = toggle_scheduled_task(task_id, enabled)
                        if task is None:
                            self._send_rpc_error(request_id, f"Task not found: {task_id}")
                        else:
                            self._send_rpc_response(request_id, task_to_dict(task))
                    except Exception as exc:
                        logger.exception("toggleScheduledTask failed")
                        self._send_rpc_error(request_id, str(exc))
                # --- Automation: Event Listeners ---
                elif method == "listEventListeners":
                    try:
                        from coding_agent.automation import list_event_listeners, listener_to_dict

                        listeners = list_event_listeners()
                        self._send_rpc_response(request_id, [listener_to_dict(listener) for listener in listeners])
                    except Exception as exc:
                        logger.exception("listEventListeners failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createEventListener":
                    try:
                        from coding_agent.automation import create_event_listener, listener_to_dict

                        listener = create_event_listener(params)
                        self._send_rpc_response(request_id, listener_to_dict(listener))
                    except Exception as exc:
                        logger.exception("createEventListener failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateEventListener":
                    try:
                        from coding_agent.automation import listener_to_dict, update_event_listener

                        listener_id = params.get("id", "")
                        listener = update_event_listener(listener_id, params)
                        if listener is None:
                            self._send_rpc_error(request_id, f"Listener not found: {listener_id}")
                        else:
                            self._send_rpc_response(request_id, listener_to_dict(listener))
                    except Exception as exc:
                        logger.exception("updateEventListener failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "deleteEventListener":
                    try:
                        from coding_agent.automation import delete_event_listener

                        listener_id = params.get("id", "")
                        ok = delete_event_listener(listener_id)
                        self._send_rpc_response(request_id, {"ok": ok})
                    except Exception as exc:
                        logger.exception("deleteEventListener failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "toggleEventListener":
                    try:
                        from coding_agent.automation import listener_to_dict, toggle_event_listener

                        listener_id = params.get("id", "")
                        enabled = params.get("enabled", True)
                        listener = toggle_event_listener(listener_id, enabled)
                        if listener is None:
                            self._send_rpc_error(request_id, f"Listener not found: {listener_id}")
                        else:
                            self._send_rpc_response(request_id, listener_to_dict(listener))
                    except Exception as exc:
                        logger.exception("toggleEventListener failed")
                        self._send_rpc_error(request_id, str(exc))
        finally:
            self._connections.discard(ws)
            if self._ws is ws:
                self._ws = None

    async def _handle_prompt(self, text: str, session_id: str = "") -> None:
        from agent_framework._types import Content, Message

        from coding_agent.loop import run_coding_agent
        from coding_agent.mcp import format_mcp_tools_for_prompt
        from coding_agent.session import dict_to_message, message_to_dict
        from coding_agent.system_prompt import (
            BuildSystemPromptOptions,
            build_system_prompt,
            discover_project_context,
        )

        # Resolve session and model
        settings = self._settings if isinstance(self._settings, Settings) else None
        primary_model = getattr(settings, "primary_model", "") if settings else ""
        existing = load_session(session_id) if session_id else None
        if existing:
            session = existing
        elif self._session is None:
            session = create_session(model=primary_model)
        else:
            session = self._session
        self._session = session
        session_model = session.model or primary_model
        if not session_id:
            save_session(session)
        session = start_session_run(session.id) or session
        self._session = session

        # Build messages (skills are advertised via SkillsProvider).
        messages: list[object] = [dict_to_message(m) for m in session.messages]
        messages.append(Message(role="user", contents=[Content(type="text", text=text)]))
        ctx = discover_project_context()
        mcp_tools_prompt = format_mcp_tools_for_prompt(self._mcp_tools)
        sys_prompt = build_system_prompt(
            BuildSystemPromptOptions(
                project_context=ctx,
                mcp_tools_prompt=mcp_tools_prompt,
                tool_approval=getattr(settings, "tool_approval", None),
            )
        )

        error_occurred = False
        use_workflow = bool(getattr(settings, "workflow_loop", False))
        approval_enabled = bool(getattr(settings, "tool_approval", {}).get("enabled", True))
        framework_session = get_or_create_framework_session(session.id)
        result: WorkflowOutput | PendingApproval | None = None
        workflow: Any = None

        def _on_event(event: AgentEvent) -> None:
            if isinstance(event, UsageEvent):
                session.input_tokens += event.input_tokens
                session.output_tokens += event.output_tokens
                session.total_tokens += event.total_tokens
                session.cache_read_tokens += event.cache_read_tokens
                session.reasoning_tokens += event.reasoning_tokens
            self._emit(event, session_id=session.id)

        try:
            provider_id, model_id = _split_selected_model(session_model)
            cfg = model_config(settings, session_model) if settings else None
            max_tok = cfg.get("contextWindow") if cfg else None
            lvl = thinking_level(settings, session_model) if settings else None
            options = thinking_options_for_model(lvl, provider_id, model_id)
            client = self._client_for(session_model)
            if use_workflow:
                from coding_agent.workflow_loop import run_coding_workflow

                result = await run_coding_workflow(
                    client=client,
                    messages=messages,  # type: ignore[arg-type]
                    tools=self._tools,
                    on_event=_on_event,
                    system_prompt=sys_prompt,
                    thinking_level=options.get("reasoning_effort") if options else None,
                    skill_provider=self._skill_provider,
                    mcp_tools=self._mcp_tools,
                    framework_session=framework_session,
                    approval_enabled=approval_enabled,
                )
                if isinstance(result, PendingApproval):
                    # PendingApproval returned — store it and wait for user response.
                    self._pending_approvals[result.call_id] = {
                        "pending": result,
                        "framework_session": framework_session,
                        "session": session,
                        "client": client,
                        "tools": self._tools,
                        "system_prompt": sys_prompt,
                        "thinking_level": options.get("reasoning_effort") if options else None,
                        "skill_provider": self._skill_provider,
                        "mcp_tools": self._mcp_tools,
                        "approval_enabled": approval_enabled,
                    }
                    save_framework_session(framework_session)
                    return
                if isinstance(result, WorkflowOutput):
                    session.messages = [message_to_dict(m) for m in result.messages]
                    self._session = session
            else:
                await run_coding_agent(
                    client=client,
                    messages=messages,  # type: ignore[arg-type]
                    tools=self._tools,
                    on_event=_on_event,
                    system_prompt=sys_prompt,
                    thinking_level=options.get("reasoning_effort") if options else None,
                    compaction_max_tokens=max_tok,
                    skill_provider=self._skill_provider,
                    mcp_tools=self._mcp_tools,
                )
        except asyncio.CancelledError:
            logger.info("Agent run cancelled")
            self._emit(ErrorEvent(message="Agent run cancelled", recoverable=True), session_id=session.id)
            self._emit(DoneEvent(), session_id=session.id)
        except Exception as exc:
            error_occurred = True
            logger.exception("Agent loop failed")
            self._emit(ErrorEvent(message=str(exc), recoverable=False), session_id=session.id)
            self._emit(DoneEvent(), session_id=session.id)
        finally:
            # 清理任务引用
            if session.id in self._current_tasks:
                del self._current_tasks[session.id]
            if result is not None and isinstance(result, WorkflowOutput):
                message_dicts = [message_to_dict(m) for m in result.messages]
            else:
                has_sys = messages and hasattr(messages[0], "role") and getattr(messages[0], "role", "") == "system"
                message_dicts = [message_to_dict(m) for m in (messages[1:] if has_sys else messages)]
            session = end_session_run(session.id, error=error_occurred) or session
            session.messages = message_dicts
            self._session = session
            save_session(session)
            save_framework_session(framework_session)
            del workflow

    async def _resume_approval(self, call_id: str, approved: bool) -> None:
        """Resume a workflow paused for tool approval."""
        from coding_agent.workflow_loop import resume_coding_workflow

        info = self._pending_approvals.pop(call_id, None)
        if info is None:
            return
        pending: PendingApproval = info["pending"]
        session = info["session"]

        def _on_event(event: AgentEvent) -> None:
            if isinstance(event, UsageEvent):
                session.input_tokens += event.input_tokens
                session.output_tokens += event.output_tokens
                session.total_tokens += event.total_tokens
                session.cache_read_tokens += event.cache_read_tokens
                session.reasoning_tokens += event.reasoning_tokens
            self._emit(event, session_id=session.id)

        try:
            result = await resume_coding_workflow(
                pending=pending,
                approved=approved,
                framework_session=info["framework_session"],
                client=info["client"],
                tools=info["tools"],
                on_event=_on_event,
                system_prompt=info.get("system_prompt"),
                thinking_level=info.get("thinking_level"),
                skill_provider=info.get("skill_provider"),
                mcp_tools=info.get("mcp_tools"),
                approval_enabled=info.get("approval_enabled", True),
            )
            if isinstance(result, PendingApproval):
                # Another approval request queued.
                self._pending_approvals[result.call_id] = {
                    "pending": result,
                    "framework_session": info["framework_session"],
                    "session": session,
                    "client": info["client"],
                    "tools": info["tools"],
                    "system_prompt": info.get("system_prompt"),
                    "thinking_level": info.get("thinking_level"),
                    "skill_provider": info.get("skill_provider"),
                    "mcp_tools": info.get("mcp_tools"),
                    "approval_enabled": info.get("approval_enabled", True),
                }
            elif isinstance(result, WorkflowOutput):
                session.messages = [message_to_dict(m) for m in result.messages]
                self._session = session
                save_session(session)
                self._emit(DoneEvent(), session_id=session.id)
        except asyncio.CancelledError:
            logger.info("Approval resume cancelled")
            self._emit(ErrorEvent(message="Agent run cancelled", recoverable=True), session_id=session.id)
            self._emit(DoneEvent(), session_id=session.id)
        except Exception as exc:
            logger.exception("Approval resume failed")
            self._emit(ErrorEvent(message=str(exc), recoverable=False), session_id=session.id)
            self._emit(DoneEvent(), session_id=session.id)
        finally:
            save_session(session)

    async def run_forever(self) -> None:
        from coding_agent.system_prompt import discover_project_context

        ctx = discover_project_context()
        logger.info("WS gateway starting — OS: %s, shell: %s", ctx.os_name, ctx.shell)
        async with serve(self._handle_ws, self._host, self._port):
            logger.info("WS gateway on ws://%s:%d", self._host, self._port)
            print(f"WS READY ws://{self._host}:{self._port}", file=sys.stderr, flush=True)
            await asyncio.get_running_loop().create_future()
