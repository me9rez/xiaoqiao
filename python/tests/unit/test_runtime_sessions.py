"""Unit tests for session metadata storage."""

from __future__ import annotations

from pathlib import Path

from xiaoqiao.bots import BotRepository
from xiaoqiao.groups import GroupRepository
from xiaoqiao.runtime.sessions import SessionRepository


def _repos(tmp_path: Path) -> tuple[BotRepository, GroupRepository, SessionRepository]:
    db = tmp_path / "agent.db"
    return BotRepository(db), GroupRepository(db), SessionRepository(db)


class TestSessionRepository:
    def test_create_and_get(self, tmp_path: Path) -> None:
        bots, _, sessions = _repos(tmp_path)
        bot = bots.create("Coder")

        session = sessions.create(bot.id, title="First")

        assert session.bot_id == bot.id
        assert session.group_id is None
        assert session.status == "idle"
        assert sessions.get(session.id) == session

    def test_group_session_is_reused(self, tmp_path: Path) -> None:
        bots, groups, sessions = _repos(tmp_path)
        bot = bots.create("Coder")
        group = groups.create("Daily", [bot.id])

        first = sessions.get_or_create(bot.id, group_id=group.id)
        second = sessions.get_or_create(bot.id, group_id=group.id)

        assert first.id == second.id

    def test_direct_sessions_are_distinct(self, tmp_path: Path) -> None:
        bots, _, sessions = _repos(tmp_path)
        bot = bots.create("Coder")

        first = sessions.get_or_create(bot.id)
        second = sessions.get_or_create(bot.id)

        assert first.id != second.id

    def test_list_filters(self, tmp_path: Path) -> None:
        bots, groups, sessions = _repos(tmp_path)
        bot = bots.create("Coder")
        first_group = groups.create("One", [bot.id])
        second_group = groups.create("Two", [bot.id])
        sessions.get_or_create(bot.id, group_id=first_group.id)
        sessions.get_or_create(bot.id, group_id=second_group.id)

        assert len(sessions.list(bot_id=bot.id)) == 2
        assert len(sessions.list(bot_id=bot.id, group_id=first_group.id)) == 1

    def test_update_watermark(self, tmp_path: Path) -> None:
        bots, _, sessions = _repos(tmp_path)
        bot = bots.create("Coder")
        session = sessions.create(bot.id)

        updated = sessions.update(session.id, last_seen_seq=42, status="running")

        assert updated is not None
        assert updated.last_seen_seq == 42
        assert updated.status == "running"

    def test_update_rejects_unknown_field(self, tmp_path: Path) -> None:
        bots, _, sessions = _repos(tmp_path)
        bot = bots.create("Coder")
        session = sessions.create(bot.id)

        try:
            sessions.update(session.id, nope=1)
        except ValueError as exc:
            assert "nope" in str(exc)
        else:  # pragma: no cover - explicit failure path
            raise AssertionError("expected ValueError")
