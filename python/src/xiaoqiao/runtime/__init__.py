"""Runtime: the always-on execution layer behind every channel.

``RunManager`` owns runs, ``SessionRepository`` persists conversation metadata
and ``EventBus`` fans out run-scoped events to gateways and channel adapters.
"""

from __future__ import annotations

from xiaoqiao.runtime.approvals import Approval, ApprovalBroker, approval_to_dict
from xiaoqiao.runtime.bus import EventBus, RuntimeEvent
from xiaoqiao.runtime.group_chat import GroupChatService
from xiaoqiao.runtime.group_messages import GroupMessage, GroupMessageRepository
from xiaoqiao.runtime.runs import RunManager, RunRequest, RunResult
from xiaoqiao.runtime.sessions import SessionRecord, SessionRepository

__all__ = [
    "Approval",
    "ApprovalBroker",
    "EventBus",
    "GroupChatService",
    "GroupMessage",
    "GroupMessageRepository",
    "RunManager",
    "RunRequest",
    "RunResult",
    "RuntimeEvent",
    "SessionRecord",
    "SessionRepository",
    "approval_to_dict",
]
