"""Unit tests for durable approvals: lifecycle, identity and expiry."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.approvals import ApprovalBroker


@pytest.fixture
def env(tmp_path: Path) -> tuple[ApprovalBroker, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return ApprovalBroker(db), bot.id


def _create(broker: ApprovalBroker, bot_id: str, *, ttl: int | None = None):
    run_id = broker.create_run(bot_id, trigger="web")
    return broker.create(run_id, "call_1", bot_id, "run_command", {"command": "ls"}, ttl_seconds=ttl)


class TestApprovalLifecycle:
    def test_create_and_get(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        approval = _create(broker, bot_id)

        assert approval.status == "pending"
        assert broker.get(approval.id) == approval
        assert broker.get_by_call_id("call_1") == approval
        assert [item.id for item in broker.list(status="pending")] == [approval.id]

    def test_approve(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        approval = _create(broker, bot_id)

        resolved, reason = broker.resolve(approval_id=approval.id, approved=True)

        assert reason == "ok"
        assert resolved is not None
        assert resolved.status == "approved"
        assert resolved.resolved_by == "owner"

    def test_deny(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        _create(broker, bot_id)

        resolved, reason = broker.resolve(call_id="call_1", approved=False)

        assert reason == "ok"
        assert resolved is not None
        assert resolved.status == "denied"

    def test_double_resolve_conflicts(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        approval = _create(broker, bot_id)
        broker.resolve(approval_id=approval.id, approved=True)

        resolved, reason = broker.resolve(approval_id=approval.id, approved=False)

        assert reason == "conflict"
        assert resolved is not None
        assert resolved.status == "approved"

    def test_only_owner_can_resolve(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        approval = _create(broker, bot_id)

        resolved, reason = broker.resolve(approval_id=approval.id, approved=True, resolved_by="bot_other")

        assert reason == "forbidden"
        assert resolved is None

    def test_unknown_approval(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, _ = env
        assert broker.resolve(approval_id="ap_missing", approved=True) == (None, "not_found")


class TestExpiry:
    def test_expired_is_marked_by_list(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        approval = _create(broker, bot_id, ttl=0)

        assert broker.expire_due() == 1
        assert broker.get(approval.id).status == "expired"  # type: ignore[union-attr]

    def test_expired_cannot_be_resolved(self, env: tuple[ApprovalBroker, str]) -> None:
        broker, bot_id = env
        approval = _create(broker, bot_id, ttl=0)

        resolved, reason = broker.resolve(approval_id=approval.id, approved=True)

        assert reason == "expired"
        assert resolved is not None
        assert resolved.status == "expired"
