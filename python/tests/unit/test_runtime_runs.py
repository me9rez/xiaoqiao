"""Unit tests for RunManager: lifecycle, serialization, cancel and events."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.bus import EventBus
from xiaoqiao.runtime.runs import RunManager, RunRequest, RunResult
from xiaoqiao.runtime.sessions import SessionRepository


@pytest.fixture
def env(tmp_path: Path) -> tuple[BotRepository, SessionRepository, Path]:
    db = tmp_path / "agent.db"
    return BotRepository(db), SessionRepository(db), db


def _req(bot_id: str, session_id: str, text: str = "hi") -> RunRequest:
    return RunRequest(bot_id=bot_id, session_id=session_id, text=text)


class TestRunLifecycle:
    @pytest.mark.asyncio
    async def test_completes_and_persists(self, env: tuple[BotRepository, SessionRepository, Path]) -> None:
        bots, sessions, db = env
        bot = bots.create("Coder")
        session = sessions.create(bot.id)
        events: list[str] = []

        async def execute(request: RunRequest, run_id: str) -> RunResult:
            return RunResult(status="done", text="ok")

        bus = EventBus()
        bus.subscribe(lambda event: events.append(event.type))
        manager = RunManager(execute, db_path=db, bus=bus)

        run_id = await manager.submit(_req(bot.id, session.id))
        status = await manager.wait(run_id, timeout=2)

        assert status == "done"
        record = manager.get(run_id)
        assert record is not None
        assert record.status == "done"
        assert record.session_id == session.id
        assert events == ["run_started", "run_finished"]

    @pytest.mark.asyncio
    async def test_failure_is_recorded(self, env: tuple[BotRepository, SessionRepository, Path]) -> None:
        bots, sessions, db = env
        bot = bots.create("Coder")
        session = sessions.create(bot.id)

        async def execute(request: RunRequest, run_id: str) -> RunResult:
            raise RuntimeError("boom")

        manager = RunManager(execute, db_path=db)
        run_id = await manager.submit(_req(bot.id, session.id))
        status = await manager.wait(run_id, timeout=2)

        assert status == "failed"
        record = manager.get(run_id)
        assert record is not None
        assert record.error == "boom"

    @pytest.mark.asyncio
    async def test_same_session_is_serialized(self, env: tuple[BotRepository, SessionRepository, Path]) -> None:
        bots, sessions, db = env
        bot = bots.create("Coder")
        session = sessions.create(bot.id)
        order: list[str] = []

        async def execute(request: RunRequest, run_id: str) -> RunResult:
            order.append(f"start:{request.text}")
            await asyncio.sleep(0.02)
            order.append(f"end:{request.text}")
            return RunResult()

        manager = RunManager(execute, db_path=db)
        first = await manager.submit(_req(bot.id, session.id, "one"))
        second = await manager.submit(_req(bot.id, session.id, "two"))

        await manager.wait(first, timeout=2)
        await manager.wait(second, timeout=2)

        assert order == ["start:one", "end:one", "start:two", "end:two"]

    @pytest.mark.asyncio
    async def test_cancel(self, env: tuple[BotRepository, SessionRepository, Path]) -> None:
        bots, sessions, db = env
        bot = bots.create("Coder")
        session = sessions.create(bot.id)

        async def execute(request: RunRequest, run_id: str) -> RunResult:
            await asyncio.sleep(10)
            return RunResult()

        manager = RunManager(execute, db_path=db)
        run_id = await manager.submit(_req(bot.id, session.id))
        await asyncio.sleep(0.01)

        assert await manager.cancel(run_id) is True
        assert await manager.wait(run_id, timeout=2) == "cancelled"

    @pytest.mark.asyncio
    async def test_list_filters(self, env: tuple[BotRepository, SessionRepository, Path]) -> None:
        bots, sessions, db = env
        bot = bots.create("Coder")
        session = sessions.create(bot.id)

        async def execute(request: RunRequest, run_id: str) -> RunResult:
            return RunResult()

        manager = RunManager(execute, db_path=db)
        run_id = await manager.submit(_req(bot.id, session.id))
        await manager.wait(run_id, timeout=2)

        assert [r.id for r in manager.list(bot_id=bot.id)] == [run_id]
        assert manager.list(status="failed") == []
