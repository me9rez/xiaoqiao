"""WebSocket gateway server — replaces stdin/stdout transport.

Usage:
    python -m xiaoqiao.main --ws-port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from websockets.asyncio.server import ServerConnection, serve

from xiaoqiao.agent_runtime import AgentRuntime, PendingApproval
from xiaoqiao.bots import BotRepository, LastBotError, bot_to_dict
from xiaoqiao.events import (
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
from xiaoqiao.groups import GroupRepository, group_to_dict
from xiaoqiao.mcp import (
    get_connector,
    install_connector,
    list_connectors,
    uninstall_connector,
    update_connector_config,
)
from xiaoqiao.runtime.approvals import ApprovalBroker, approval_to_dict
from xiaoqiao.runtime.group_chat import GroupChatService, render_group_context
from xiaoqiao.runtime.group_messages import GroupMessageRepository, message_to_dict
from xiaoqiao.runtime.sessions import SessionRepository
from xiaoqiao.session import (
    create_session,
    delete_session,
    end_session_run,
    list_sessions,
    load_session,
    save_session,
    start_session_run,
    update_session,
)
from xiaoqiao.settings import Settings, _split_selected_model, build_client, thinking_level
from xiaoqiao.settings import load as load_settings
from xiaoqiao.settings import save as save_settings
from xiaoqiao.skills import (
    get_skill,
    get_skill_file_content,
    get_skill_files,
    install_skill,
    list_skills,
    toggle_skill,
    uninstall_skill,
    update_skill,
)
from xiaoqiao.thinking import thinking_options_for_model
from xiaoqiao.turn_runner import TurnRunner

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
        "botId": getattr(info, "bot_id", ""),
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
        "botId": getattr(session, "bot_id", ""),
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
        self._bots = BotRepository()
        self._groups = GroupRepository()
        self._group_messages = GroupMessageRepository()
        self._sessions_db = SessionRepository()
        self._approvals = ApprovalBroker()
        self._session: Any = None
        self._ws: ServerConnection | None = None
        self._emit_tasks: list[asyncio.Task[None]] = []
        self._clients: dict[str, Any] = {}
        self._connections: set[ServerConnection] = set()
        self._workspace = self._detect_workspace()
        self._pending_approvals: dict[str, Any] = {}
        self._turn_runner = TurnRunner(
            tools=self._tools,
            settings=settings,
            skill_provider=skill_provider,
            mcp_tools=self._mcp_tools,
        )

    def _client_for(self, model: str) -> Any:
        if self._settings is None:
            raise RuntimeError("Settings not available")
        if model not in self._clients:
            self._clients[model] = build_client(self._settings, model)
        return self._clients[model]

    def _detect_workspace(self) -> dict[str, str]:
        from xiaoqiao.system_prompt import discover_project_context

        ctx = discover_project_context()
        path = ctx.cwd or str(Path.cwd().resolve())
        return {"name": Path(path).name, "path": path}

    def _emit(self, event: AgentEvent, session_id: str = "", group_id: str = "") -> None:
        obj = _serialize_event(event)
        if session_id:
            obj["sessionId"] = session_id
        if group_id:
            obj["groupId"] = group_id
        if obj.get("type") not in ("text_delta", "thinking_delta", "tool_execution_delta"):
            fields = _summarize_event(obj)
            print(f"→ {obj.get('type', '?')} {fields}", file=sys.stderr, flush=True)
        self._broadcast(obj)

    def _broadcast(self, obj: dict[str, Any]) -> None:
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

    def _emit_group_message(self, group_id: str, message: Any) -> None:
        self._broadcast(
            {
                "type": "group_message_created",
                "groupId": group_id,
                "message": message_to_dict(message),
            }
        )

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
                    bot_id = params.get("botId", "")
                    group_id = params.get("groupId", "")
                    logger.info(
                        "← prompt (bot=%s, group=%s, session=%s, text=%.80s)",
                        bot_id,
                        group_id,
                        session_id,
                        text,
                    )
                    if group_id:
                        self._current_tasks[group_id] = asyncio.create_task(self._handle_group_prompt(group_id, text))
                    else:
                        self._current_tasks[session_id] = asyncio.create_task(
                            self._handle_prompt(text, session_id, bot_id)
                        )
                elif method == "cancel":
                    session_id = params.get("sessionId", "")
                    if session_id and session_id in self._current_tasks:
                        task = self._current_tasks[session_id]
                        if not task.done():
                            task.cancel()
                elif method == "listSessions":
                    try:
                        sessions = list_sessions()
                        bot_id = params.get("botId", "")
                        if bot_id:
                            sessions = [session for session in sessions if getattr(session, "bot_id", "") == bot_id]
                        self._send_rpc_response(request_id, [_session_info_to_dict(s) for s in sessions])
                    except Exception as exc:
                        logger.exception("listSessions failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createSession":
                    try:
                        title = params.get("title", "")
                        model = params.get("model", "")
                        workspace = params.get("workspace", "")
                        bot_id = params.get("botId", "")
                        session = create_session(title=title, model=model, workspace=workspace, bot_id=bot_id)
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
                elif method == "listBots":
                    try:
                        self._bots.ensure_default()
                        self._send_rpc_response(request_id, [bot_to_dict(bot) for bot in self._bots.list()])
                    except Exception as exc:
                        logger.exception("listBots failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createBot":
                    try:
                        bot = self._bots.create(
                            params["name"],
                            emoji=params.get("emoji", "🤖"),
                            persona=params.get("persona", ""),
                            model=params.get("model", ""),
                            workspace=params.get("workspace", ""),
                        )
                        self._send_rpc_response(request_id, bot_to_dict(bot))
                    except Exception as exc:
                        logger.exception("createBot failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateBot":
                    try:
                        bot_id = params.pop("botId", "")
                        bot = self._bots.update(bot_id, **params)
                        if bot is None:
                            self._send_rpc_error(request_id, f"Bot not found: {bot_id}")
                        else:
                            self._send_rpc_response(request_id, bot_to_dict(bot))
                    except Exception as exc:
                        logger.exception("updateBot failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "deleteBot":
                    try:
                        bot_id = params.get("botId", "")
                        self._send_rpc_response(request_id, {"ok": self._bots.delete(bot_id)})
                    except LastBotError as exc:
                        self._send_rpc_error(request_id, str(exc))
                    except Exception as exc:
                        logger.exception("deleteBot failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "listGroups":
                    try:
                        groups = self._groups.list(include_archived=bool(params.get("includeArchived", False)))
                        self._send_rpc_response(request_id, [group_to_dict(group) for group in groups])
                    except Exception as exc:
                        logger.exception("listGroups failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createGroup":
                    try:
                        group = self._groups.create(
                            params["name"],
                            list(params.get("botIds", [])),
                            default_bot_id=params.get("defaultBotId") or None,
                            settings=params.get("settings"),
                        )
                        self._send_rpc_response(request_id, group_to_dict(group))
                    except Exception as exc:
                        logger.exception("createGroup failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateGroup":
                    try:
                        group_id = params.pop("groupId", "")
                        group = self._groups.update(group_id, **params)
                        if group is None:
                            self._send_rpc_error(request_id, f"Group not found: {group_id}")
                        else:
                            self._send_rpc_response(request_id, group_to_dict(group))
                    except Exception as exc:
                        logger.exception("updateGroup failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "deleteGroup":
                    try:
                        group_id = params.get("groupId", "")
                        self._send_rpc_response(request_id, {"ok": self._groups.delete(group_id)})
                    except Exception as exc:
                        logger.exception("deleteGroup failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "addGroupMember":
                    try:
                        group = self._groups.add_bot(params.get("groupId", ""), params.get("botId", ""))
                        if group is None:
                            self._send_rpc_error(request_id, "Group not found")
                        else:
                            self._send_rpc_response(request_id, group_to_dict(group))
                    except Exception as exc:
                        logger.exception("addGroupMember failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "removeGroupMember":
                    try:
                        group = self._groups.remove_bot(params.get("groupId", ""), params.get("botId", ""))
                        if group is None:
                            self._send_rpc_error(request_id, "Group not found")
                        else:
                            self._send_rpc_response(request_id, group_to_dict(group))
                    except Exception as exc:
                        logger.exception("removeGroupMember failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "listGroupMessages":
                    try:
                        group_id = params.get("groupId", "")
                        limit = int(params.get("limit", 100))
                        before_seq = params.get("beforeSeq")
                        items = self._group_messages.list(
                            group_id,
                            limit=limit,
                            before_seq=int(before_seq) if before_seq is not None else None,
                        )
                        self._send_rpc_response(request_id, [message_to_dict(item) for item in items])
                    except Exception as exc:
                        logger.exception("listGroupMessages failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "listApprovals":
                    try:
                        items = self._approvals.list(status=params.get("status") or None)
                        self._send_rpc_response(request_id, [approval_to_dict(item) for item in items])
                    except Exception as exc:
                        logger.exception("listApprovals failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "approval_response":
                    call_id = params.get("callId", "")
                    approved = bool(params.get("approved", False))
                    session_id = params.get("sessionId", "")
                    approval, reason = self._approvals.resolve(call_id=call_id, approved=approved)
                    if reason != "ok":
                        self._send_rpc_error(request_id, f"Cannot resolve approval: {reason}")
                    else:
                        self._broadcast_approval_resolved(approval)
                        if call_id in self._pending_approvals:
                            task = asyncio.create_task(self._resume_approval(call_id, approved))
                            if session_id:
                                self._current_tasks[session_id] = task
                        else:
                            self._send_rpc_response(
                                request_id, {"ok": True, "status": approval.status if approval else ""}
                            )
                elif method == "resolveApproval":
                    approval_id = params.get("approvalId", "")
                    approved = bool(params.get("approved", False))
                    approval, reason = self._approvals.resolve(approval_id=approval_id, approved=approved)
                    if reason != "ok":
                        self._send_rpc_error(request_id, f"Cannot resolve approval: {reason}")
                    else:
                        self._broadcast_approval_resolved(approval)
                        if approval is not None and approval.call_id in self._pending_approvals:
                            task = asyncio.create_task(self._resume_approval(approval.call_id, approved))
                            self._emit_tasks.append(task)
                            task.add_done_callback(self._emit_tasks.remove)
                        self._send_rpc_response(request_id, {"ok": True, "status": approval.status if approval else ""})
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
                        from xiaoqiao.automation import list_scheduled_tasks, task_to_dict

                        tasks = list_scheduled_tasks()
                        self._send_rpc_response(request_id, [task_to_dict(t) for t in tasks])
                    except Exception as exc:
                        logger.exception("listScheduledTasks failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createScheduledTask":
                    try:
                        from xiaoqiao.automation import create_scheduled_task, task_to_dict

                        task = create_scheduled_task(params)
                        self._send_rpc_response(request_id, task_to_dict(task))
                    except Exception as exc:
                        logger.exception("createScheduledTask failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateScheduledTask":
                    try:
                        from xiaoqiao.automation import task_to_dict, update_scheduled_task

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
                        from xiaoqiao.automation import delete_scheduled_task

                        task_id = params.get("id", "")
                        ok = delete_scheduled_task(task_id)
                        self._send_rpc_response(request_id, {"ok": ok})
                    except Exception as exc:
                        logger.exception("deleteScheduledTask failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "toggleScheduledTask":
                    try:
                        from xiaoqiao.automation import task_to_dict, toggle_scheduled_task

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
                        from xiaoqiao.automation import list_event_listeners, listener_to_dict

                        listeners = list_event_listeners()
                        self._send_rpc_response(request_id, [listener_to_dict(listener) for listener in listeners])
                    except Exception as exc:
                        logger.exception("listEventListeners failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "createEventListener":
                    try:
                        from xiaoqiao.automation import create_event_listener, listener_to_dict

                        listener = create_event_listener(params)
                        self._send_rpc_response(request_id, listener_to_dict(listener))
                    except Exception as exc:
                        logger.exception("createEventListener failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "updateEventListener":
                    try:
                        from xiaoqiao.automation import listener_to_dict, update_event_listener

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
                        from xiaoqiao.automation import delete_event_listener

                        listener_id = params.get("id", "")
                        ok = delete_event_listener(listener_id)
                        self._send_rpc_response(request_id, {"ok": ok})
                    except Exception as exc:
                        logger.exception("deleteEventListener failed")
                        self._send_rpc_error(request_id, str(exc))
                elif method == "toggleEventListener":
                    try:
                        from xiaoqiao.automation import listener_to_dict, toggle_event_listener

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

    async def _handle_prompt(self, text: str, session_id: str = "", bot_id: str = "") -> None:
        from xiaoqiao.mcp import format_mcp_tools_for_prompt
        from xiaoqiao.system_prompt import (
            BuildSystemPromptOptions,
            build_system_prompt,
            discover_project_context,
        )

        # Resolve the bot first: persona, model and workspace all come from it.
        settings = self._settings if isinstance(self._settings, Settings) else None
        primary_model = getattr(settings, "primary_model", "") if settings else ""
        bot = self._bots.get(bot_id) if bot_id else self._bots.ensure_default()
        if bot is None:
            self._emit(ErrorEvent(message=f"Bot not found: {bot_id}", recoverable=False))
            self._emit(DoneEvent())
            return
        default_model = bot.model or primary_model

        existing = load_session(session_id) if session_id else None
        if existing:
            session = existing
            if not session.bot_id:
                # Legacy sessions predate bots: claim them for whichever bot is in use.
                update_session(session.id, bot_id=bot.id)
                session.bot_id = bot.id
        elif self._session is None:
            session = create_session(model=default_model, bot_id=bot.id)
        else:
            session = self._session
        self._session = session
        session_model = session.model or default_model
        if not session_id:
            save_session(session)
        session = start_session_run(session.id) or session
        self._session = session

        ctx = discover_project_context(bot.workspace or None)
        mcp_tools_prompt = format_mcp_tools_for_prompt(self._mcp_tools)
        sys_prompt = build_system_prompt(
            BuildSystemPromptOptions(
                persona=bot.persona,
                bot_name=bot.name,
                project_context=ctx,
                mcp_tools_prompt=mcp_tools_prompt,
                tool_approval=getattr(settings, "tool_approval", None),
            )
        )

        error_occurred = False
        approval_enabled = bool(getattr(settings, "tool_approval", {}).get("enabled", True))

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
            lvl = thinking_level(settings, session_model) if settings else None
            options = thinking_options_for_model(lvl, provider_id, model_id)
            client = self._client_for(session_model)

            runtime = self._runtime_for(session, client, sys_prompt, options, settings, approval_enabled)
            outcome = await runtime.run_turn(text, _on_event)

            if outcome.pending_approval is not None:
                pending = outcome.pending_approval
                approval = self._record_approval(pending, bot)
                self._pending_approvals[pending.call_id] = {
                    "runtime": runtime,
                    "pending": pending,
                    "session": session,
                    "approval_id": approval.id,
                }
                self._remember_runtime(session, runtime)
                save_session(session)
                return

            self._remember_runtime(session, runtime)
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
            session = end_session_run(session.id, error=error_occurred) or session
            self._session = session
            save_session(session)

    async def _handle_group_prompt(self, group_id: str, text: str) -> None:
        chat = GroupChatService(self._bots, self._groups, self._sessions_db, self._group_messages)

        async def execute(bot: Any, session: Any, messages: list[Any]) -> str:
            return await self._execute_group_bot(bot, session, messages, group_id)

        try:
            appended = await chat.handle_user_message(group_id, text, execute)
            for message in appended:
                self._emit_group_message(group_id, message)
        except asyncio.CancelledError:
            logger.info("Group prompt cancelled: %s", group_id)
        except Exception as exc:
            logger.exception("Group prompt failed")
            self._emit(ErrorEvent(message=str(exc), recoverable=False), group_id=group_id)
        finally:
            self._current_tasks.pop(group_id, None)

    async def _execute_group_bot(
        self,
        bot: Any,
        session: Any,
        messages: list[Any],
        group_id: str,
    ) -> str:
        """Run one bot turn against the new group messages and return its text."""
        from xiaoqiao.framework_session import save_framework_session
        from xiaoqiao.mcp import format_mcp_tools_for_prompt
        from xiaoqiao.system_prompt import (
            BuildSystemPromptOptions,
            build_system_prompt,
            discover_project_context,
        )

        settings = self._settings if isinstance(self._settings, Settings) else None
        primary_model = getattr(settings, "primary_model", "") if settings else ""
        session_model = session.model or bot.model or primary_model
        names = {item.id: item.name for item in self._bots.list()}
        prompt_block = render_group_context(bot, messages, names)
        ctx = discover_project_context(bot.workspace or None)
        sys_prompt = build_system_prompt(
            BuildSystemPromptOptions(
                persona=bot.persona,
                bot_name=bot.name,
                project_context=ctx,
                mcp_tools_prompt=format_mcp_tools_for_prompt(self._mcp_tools),
                tool_approval=getattr(settings, "tool_approval", None),
            )
        )

        provider_id, model_id = _split_selected_model(session_model)
        level = thinking_level(settings, session_model) if settings else None
        options = thinking_options_for_model(level, provider_id, model_id)
        client = self._client_for(session_model)

        def _on_event(event: AgentEvent) -> None:
            self._emit(event, session_id=session.id, group_id=group_id)

        runtime = self._runtime_for(
            session,
            client,
            sys_prompt,
            options,
            settings,
            bool(getattr(settings, "tool_approval", {}).get("enabled", True)) if settings else True,
        )
        outcome = await runtime.run_turn(prompt_block, _on_event)
        save_framework_session(runtime.agent_session)
        if outcome.pending_approval is not None:
            pending = outcome.pending_approval
            approval = self._record_approval(pending, bot, group_id=group_id)
            self._pending_approvals[pending.call_id] = {
                "runtime": runtime,
                "pending": pending,
                "session": session,
                "group_id": group_id,
                "approval_id": approval.id,
            }
            return "（需要你审批后才能继续）"
        return outcome.text

    def _record_approval(self, pending: PendingApproval, bot: Any, *, group_id: str = "") -> Any:
        """Persist the approval and announce it with the durable approval id."""
        run_id = self._approvals.create_run(
            bot.id,
            group_id=group_id or None,
            trigger="group" if group_id else "web",
        )
        approval = self._approvals.create(
            run_id,
            pending.call_id,
            bot.id,
            pending.name,
            pending.arguments,
            group_id=group_id or None,
        )
        self._broadcast(
            {
                "type": "approval_requested",
                "approvalId": approval.id,
                "callId": pending.call_id,
                "botId": bot.id,
                "groupId": group_id or None,
                "runId": run_id,
                "tool": pending.name,
                "arguments": pending.arguments,
                "expiresAt": approval.expires_at,
            }
        )
        return approval

    def _broadcast_approval_resolved(self, approval: Any) -> None:
        if approval is None:
            return
        self._broadcast(
            {
                "type": "approval_resolved",
                "approvalId": approval.id,
                "callId": approval.call_id,
                "botId": approval.bot_id,
                "groupId": approval.group_id,
                "status": approval.status,
            }
        )

    def _remember_runtime(self, session: Any, runtime: AgentRuntime) -> None:
        """Persist both the display transcript and the framework session state.

        The JSONL transcript feeds the UI/history; the framework session holds the
        tool_call/tool_result pairing the model needs, so it must be saved too.
        Group sessions are database records without a transcript field, so only
        the framework snapshot applies there.
        """
        if hasattr(session, "messages"):
            self._turn_runner.remember(session, runtime)
            return
        from xiaoqiao.framework_session import save_framework_session

        save_framework_session(runtime.agent_session)

    def _runtime_for(
        self,
        session: Any,
        client: Any,
        sys_prompt: str,
        options: dict[str, Any] | None,
        settings: Settings | None,
        approval_enabled: bool,
    ) -> AgentRuntime:
        """Build (or reuse) the runtime for a xiaoqiao session.

        The framework session holds the conversation, so the runtime must stay
        stable across turns — including across an approval pause/resume.
        """
        return self._turn_runner.runtime_for(
            session_id=session.id,
            model=session.model,
            instructions=sys_prompt,
            thinking_level=(options or {}).get("reasoning_effort"),
            client=client,
            on_event=lambda _event: None,
        )

    async def _resume_approval(self, call_id: str, approved: bool) -> None:
        """Resume a turn paused for tool approval."""
        info = self._pending_approvals.pop(call_id, None)
        if info is None:
            return
        runtime: AgentRuntime = info["runtime"]
        pending: PendingApproval = info["pending"]
        session = info["session"]
        group_id = info.get("group_id", "")

        def _on_event(event: AgentEvent) -> None:
            if isinstance(event, UsageEvent) and hasattr(session, "input_tokens"):
                session.input_tokens += event.input_tokens
                session.output_tokens += event.output_tokens
                session.total_tokens += event.total_tokens
                session.cache_read_tokens += event.cache_read_tokens
                session.reasoning_tokens += event.reasoning_tokens
            self._emit(event, session_id=session.id, group_id=group_id)

        try:
            outcome = await runtime.resolve_approval(pending.call_id, approved, _on_event)
            if outcome.pending_approval is not None:
                # Another approval request queued.
                self._pending_approvals[outcome.pending_approval.call_id] = {
                    "runtime": runtime,
                    "pending": outcome.pending_approval,
                    "session": session,
                    "group_id": group_id,
                }
            self._remember_runtime(session, runtime)
            self._save_session_if_jsonl(session)
        except asyncio.CancelledError:
            logger.info("Approval resume cancelled")
            self._emit(ErrorEvent(message="Agent run cancelled", recoverable=True), session_id=session.id)
            self._emit(DoneEvent(), session_id=session.id)
        except Exception as exc:
            logger.exception("Approval resume failed")
            self._emit(ErrorEvent(message=str(exc), recoverable=False), session_id=session.id)
            self._emit(DoneEvent(), session_id=session.id)
        finally:
            self._save_session_if_jsonl(session)

    def _save_session_if_jsonl(self, session: Any) -> None:
        if hasattr(session, "messages"):
            save_session(session)

    async def run_forever(self) -> None:
        from xiaoqiao.system_prompt import discover_project_context

        ctx = discover_project_context()
        logger.info("WS gateway starting — OS: %s, shell: %s", ctx.os_name, ctx.shell)
        async with serve(self._handle_ws, self._host, self._port):
            logger.info("WS gateway on ws://%s:%d", self._host, self._port)
            print(f"WS READY ws://{self._host}:{self._port}", file=sys.stderr, flush=True)
            await asyncio.get_running_loop().create_future()
