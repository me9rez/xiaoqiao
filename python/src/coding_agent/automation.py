"""Automation module — scheduled tasks and event listeners."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _automation_dir() -> Path:
    d = Path.home() / ".coding-agent" / "automation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tasks_file() -> Path:
    return _automation_dir() / "scheduled_tasks.json"


def _listeners_file() -> Path:
    return _automation_dir() / "event_listeners.json"


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError, OSError:
        return []


def _save_json(path: Path, items: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Scheduled Task
# ---------------------------------------------------------------------------


@dataclass
class ScheduledTask:
    id: str
    name: str
    description: str
    command: str
    frequency: str  # "hourly" | "daily" | "weekly" | "weekdays" | "manual"
    time_hour: int
    time_minute: int
    skill: str
    project: str
    workspace_path: str
    push_channel: str
    enabled: bool
    run_count: int
    created_at: str
    updated_at: str


def _task_from_dict(d: dict[str, Any]) -> ScheduledTask:
    return ScheduledTask(
        id=d.get("id", ""),
        name=d.get("name", ""),
        description=d.get("description", ""),
        command=d.get("command", ""),
        frequency=d.get("frequency", "daily"),
        time_hour=d.get("time_hour", 9),
        time_minute=d.get("time_minute", 0),
        skill=d.get("skill", ""),
        project=d.get("project", ""),
        workspace_path=d.get("workspace_path", ""),
        push_channel=d.get("push_channel", ""),
        enabled=d.get("enabled", True),
        run_count=d.get("run_count", 0),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def task_to_dict(t: ScheduledTask) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "command": t.command,
        "frequency": t.frequency,
        "timeHour": t.time_hour,
        "timeMinute": t.time_minute,
        "skill": t.skill,
        "project": t.project,
        "workspacePath": t.workspace_path,
        "pushChannel": t.push_channel,
        "enabled": t.enabled,
        "runCount": t.run_count,
        "createdAt": t.created_at,
        "updatedAt": t.updated_at,
    }


def list_scheduled_tasks() -> list[ScheduledTask]:
    return [_task_from_dict(d) for d in _load_json(_tasks_file())]


def get_scheduled_task(task_id: str) -> ScheduledTask | None:
    for d in _load_json(_tasks_file()):
        if d.get("id") == task_id:
            return _task_from_dict(d)
    return None


def create_scheduled_task(data: dict[str, Any]) -> ScheduledTask:
    now = _now_iso()
    task = ScheduledTask(
        id=uuid.uuid4().hex[:12],
        name=data.get("name", ""),
        description=data.get("description", ""),
        command=data.get("command", ""),
        frequency=data.get("frequency", "daily"),
        time_hour=data.get("timeHour", data.get("time_hour", 9)),
        time_minute=data.get("timeMinute", data.get("time_minute", 0)),
        skill=data.get("skill", ""),
        project=data.get("project", ""),
        workspace_path=data.get("workspacePath", data.get("workspace_path", "")),
        push_channel=data.get("pushChannel", data.get("push_channel", "")),
        enabled=data.get("enabled", True),
        run_count=0,
        created_at=now,
        updated_at=now,
    )
    items = _load_json(_tasks_file())
    items.append(asdict(task))
    _save_json(_tasks_file(), items)
    return task


def update_scheduled_task(task_id: str, patch: dict[str, Any]) -> ScheduledTask | None:
    items = _load_json(_tasks_file())
    for i, d in enumerate(items):
        if d.get("id") == task_id:
            if "name" in patch:
                d["name"] = patch["name"]
            if "description" in patch:
                d["description"] = patch["description"]
            if "command" in patch:
                d["command"] = patch["command"]
            if "frequency" in patch:
                d["frequency"] = patch["frequency"]
            if "timeHour" in patch or "time_hour" in patch:
                d["time_hour"] = patch.get("timeHour", patch.get("time_hour", d["time_hour"]))
            if "timeMinute" in patch or "time_minute" in patch:
                d["time_minute"] = patch.get("timeMinute", patch.get("time_minute", d["time_minute"]))
            if "skill" in patch:
                d["skill"] = patch["skill"]
            if "project" in patch:
                d["project"] = patch["project"]
            if "workspacePath" in patch or "workspace_path" in patch:
                d["workspace_path"] = patch.get("workspacePath", patch.get("workspace_path", d["workspace_path"]))
            if "pushChannel" in patch or "push_channel" in patch:
                d["push_channel"] = patch.get("pushChannel", patch.get("push_channel", d["push_channel"]))
            if "enabled" in patch:
                d["enabled"] = patch["enabled"]
            d["updated_at"] = _now_iso()
            items[i] = d
            _save_json(_tasks_file(), items)
            return _task_from_dict(d)
    return None


def delete_scheduled_task(task_id: str) -> bool:
    items = _load_json(_tasks_file())
    new_items = [d for d in items if d.get("id") != task_id]
    if len(new_items) < len(items):
        _save_json(_tasks_file(), new_items)
        return True
    return False


def toggle_scheduled_task(task_id: str, enabled: bool) -> ScheduledTask | None:
    return update_scheduled_task(task_id, {"enabled": enabled})


# ---------------------------------------------------------------------------
# Event Listener
# ---------------------------------------------------------------------------


@dataclass
class EventListener:
    id: str
    name: str
    description: str
    trigger_type: str  # "http" | "file_change" | "scheduled" | "im_message"
    command: str
    trigger_condition: str  # "all" | "keyword" | "regex"
    debounce_seconds: int
    quiet_hours: bool
    push_result: bool
    skill: str
    project: str
    enabled: bool
    run_count: int
    created_at: str
    updated_at: str
    # file_change specific
    watch_path: str
    watch_events: list[str]
    file_name_pattern: str
    # scheduled specific
    interval_seconds: int
    # im_message specific
    im_channel: str
    im_scope: str  # "mention" | "private" | "all"
    group_id: str
    sender_match: str


def _listener_from_dict(d: dict[str, Any]) -> EventListener:
    return EventListener(
        id=d.get("id", ""),
        name=d.get("name", ""),
        description=d.get("description", ""),
        trigger_type=d.get("trigger_type", "http"),
        command=d.get("command", ""),
        trigger_condition=d.get("trigger_condition", "all"),
        debounce_seconds=d.get("debounce_seconds", 300),
        quiet_hours=d.get("quiet_hours", False),
        push_result=d.get("push_result", False),
        skill=d.get("skill", ""),
        project=d.get("project", ""),
        enabled=d.get("enabled", True),
        run_count=d.get("run_count", 0),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
        watch_path=d.get("watch_path", ""),
        watch_events=d.get("watch_events", []),
        file_name_pattern=d.get("file_name_pattern", ""),
        interval_seconds=d.get("interval_seconds", 60),
        im_channel=d.get("im_channel", ""),
        im_scope=d.get("im_scope", "mention"),
        group_id=d.get("group_id", ""),
        sender_match=d.get("sender_match", ""),
    )


def listener_to_dict(listener: EventListener) -> dict[str, Any]:
    return {
        "id": listener.id,
        "name": listener.name,
        "description": listener.description,
        "triggerType": listener.trigger_type,
        "command": listener.command,
        "triggerCondition": listener.trigger_condition,
        "debounceSeconds": listener.debounce_seconds,
        "quietHours": listener.quiet_hours,
        "pushResult": listener.push_result,
        "skill": listener.skill,
        "project": listener.project,
        "enabled": listener.enabled,
        "runCount": listener.run_count,
        "createdAt": listener.created_at,
        "updatedAt": listener.updated_at,
        "watchPath": listener.watch_path,
        "watchEvents": listener.watch_events,
        "fileNamePattern": listener.file_name_pattern,
        "intervalSeconds": listener.interval_seconds,
        "imChannel": listener.im_channel,
        "imScope": listener.im_scope,
        "groupId": listener.group_id,
        "senderMatch": listener.sender_match,
    }


def list_event_listeners() -> list[EventListener]:
    return [_listener_from_dict(d) for d in _load_json(_listeners_file())]


def get_event_listener(listener_id: str) -> EventListener | None:
    for d in _load_json(_listeners_file()):
        if d.get("id") == listener_id:
            return _listener_from_dict(d)
    return None


def create_event_listener(data: dict[str, Any]) -> EventListener:
    now = _now_iso()
    listener = EventListener(
        id=uuid.uuid4().hex[:12],
        name=data.get("name", ""),
        description=data.get("description", ""),
        trigger_type=data.get("triggerType", data.get("trigger_type", "http")),
        command=data.get("command", ""),
        trigger_condition=data.get("triggerCondition", data.get("trigger_condition", "all")),
        debounce_seconds=data.get("debounceSeconds", data.get("debounce_seconds", 300)),
        quiet_hours=data.get("quietHours", data.get("quiet_hours", False)),
        push_result=data.get("pushResult", data.get("push_result", False)),
        skill=data.get("skill", ""),
        project=data.get("project", ""),
        enabled=data.get("enabled", True),
        run_count=0,
        created_at=now,
        updated_at=now,
        watch_path=data.get("watchPath", data.get("watch_path", "")),
        watch_events=data.get("watchEvents", data.get("watch_events", [])),
        file_name_pattern=data.get("fileNamePattern", data.get("file_name_pattern", "")),
        interval_seconds=data.get("intervalSeconds", data.get("interval_seconds", 60)),
        im_channel=data.get("imChannel", data.get("im_channel", "")),
        im_scope=data.get("imScope", data.get("im_scope", "mention")),
        group_id=data.get("groupId", data.get("group_id", "")),
        sender_match=data.get("senderMatch", data.get("sender_match", "")),
    )
    items = _load_json(_listeners_file())
    items.append(asdict(listener))
    _save_json(_listeners_file(), items)
    return listener


def update_event_listener(listener_id: str, patch: dict[str, Any]) -> EventListener | None:
    items = _load_json(_listeners_file())
    for i, d in enumerate(items):
        if d.get("id") == listener_id:
            if "name" in patch:
                d["name"] = patch["name"]
            if "description" in patch:
                d["description"] = patch["description"]
            if "triggerType" in patch or "trigger_type" in patch:
                d["trigger_type"] = patch.get("triggerType", patch.get("trigger_type", d["trigger_type"]))
            if "command" in patch:
                d["command"] = patch["command"]
            if "triggerCondition" in patch or "trigger_condition" in patch:
                d["trigger_condition"] = patch.get(
                    "triggerCondition", patch.get("trigger_condition", d["trigger_condition"])
                )
            if "debounceSeconds" in patch or "debounce_seconds" in patch:
                d["debounce_seconds"] = patch.get(
                    "debounceSeconds", patch.get("debounce_seconds", d["debounce_seconds"])
                )
            if "quietHours" in patch or "quiet_hours" in patch:
                d["quiet_hours"] = patch.get("quietHours", patch.get("quiet_hours", d["quiet_hours"]))
            if "pushResult" in patch or "push_result" in patch:
                d["push_result"] = patch.get("pushResult", patch.get("push_result", d["push_result"]))
            if "skill" in patch:
                d["skill"] = patch["skill"]
            if "project" in patch:
                d["project"] = patch["project"]
            if "enabled" in patch:
                d["enabled"] = patch["enabled"]
            if "watchPath" in patch or "watch_path" in patch:
                d["watch_path"] = patch.get("watchPath", patch.get("watch_path", d["watch_path"]))
            if "watchEvents" in patch or "watch_events" in patch:
                d["watch_events"] = patch.get("watchEvents", patch.get("watch_events", d["watch_events"]))
            if "fileNamePattern" in patch or "file_name_pattern" in patch:
                d["file_name_pattern"] = patch.get(
                    "fileNamePattern", patch.get("file_name_pattern", d["file_name_pattern"])
                )
            if "intervalSeconds" in patch or "interval_seconds" in patch:
                d["interval_seconds"] = patch.get(
                    "intervalSeconds", patch.get("interval_seconds", d["interval_seconds"])
                )
            if "imChannel" in patch or "im_channel" in patch:
                d["im_channel"] = patch.get("imChannel", patch.get("im_channel", d["im_channel"]))
            if "imScope" in patch or "im_scope" in patch:
                d["im_scope"] = patch.get("imScope", patch.get("im_scope", d["im_scope"]))
            if "groupId" in patch or "group_id" in patch:
                d["group_id"] = patch.get("groupId", patch.get("group_id", d["group_id"]))
            if "senderMatch" in patch or "sender_match" in patch:
                d["sender_match"] = patch.get("senderMatch", patch.get("sender_match", d["sender_match"]))
            d["updated_at"] = _now_iso()
            items[i] = d
            _save_json(_listeners_file(), items)
            return _listener_from_dict(d)
    return None


def delete_event_listener(listener_id: str) -> bool:
    items = _load_json(_listeners_file())
    new_items = [d for d in items if d.get("id") != listener_id]
    if len(new_items) < len(items):
        _save_json(_listeners_file(), new_items)
        return True
    return False


def toggle_event_listener(listener_id: str, enabled: bool) -> EventListener | None:
    return update_event_listener(listener_id, {"enabled": enabled})
