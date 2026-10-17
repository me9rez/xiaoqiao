"""Unit tests for schedule computation and the routine scheduler."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.routines import RoutineRepository
from xiaoqiao.scheduler import Scheduler, compute_next_run

NOW = datetime(2026, 10, 18, 1, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path: Path) -> tuple[RoutineRepository, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return RoutineRepository(db), bot.id


class TestComputeNext:
    def test_daily_in_timezone(self) -> None:
        # 09:00 Asia/Shanghai == 01:00 UTC; at 01:00 UTC the next run is tomorrow.
        schedule = {"kind": "daily", "at": "09:00", "tz": "Asia/Shanghai"}
        assert compute_next_run(schedule, NOW) == NOW + timedelta(days=1)

    def test_daily_later_today(self) -> None:
        schedule = {"kind": "daily", "at": "10:00", "tz": "Asia/Shanghai"}
        assert compute_next_run(schedule, NOW) == NOW + timedelta(hours=1)

    def test_interval(self) -> None:
        assert compute_next_run({"kind": "interval", "minutes": 15}, NOW) == NOW + timedelta(minutes=15)

    def test_once_in_past_is_none(self) -> None:
        past = (NOW - timedelta(hours=1)).isoformat()
        assert compute_next_run({"kind": "once", "at": past}, NOW) is None

    def test_once_in_future(self) -> None:
        future = (NOW + timedelta(hours=2)).isoformat()
        assert compute_next_run({"kind": "once", "at": future}, NOW) == NOW + timedelta(hours=2)

    def test_invalid_schedule(self) -> None:
        assert compute_next_run({"kind": "daily", "at": "oops"}, NOW) is None
        assert compute_next_run({"kind": "unknown"}, NOW) is None


class TestScheduler:
    @pytest.mark.asyncio
    async def test_due_routine_fires_once(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        routine = routines.create(
            bot_id,
            "日报",
            {"kind": "interval", "minutes": 30},
            "写日报",
            next_run_at=(NOW - timedelta(minutes=1)).isoformat(),
        )
        fired: list[tuple[str, str]] = []

        async def on_fire(item, scheduled_at: str) -> None:
            fired.append((item.id, scheduled_at))

        scheduler = Scheduler(routines, on_fire, now=lambda: NOW)
        assert await scheduler.tick(NOW) == [routine.id]
        await asyncio.sleep(0.05)

        assert fired == [(routine.id, routine.next_run_at)]
        updated = routines.get(routine.id)
        assert updated is not None
        assert updated.last_run_at == routine.next_run_at
        assert updated.next_run_at is not None
        assert datetime.fromisoformat(updated.next_run_at) > NOW

        # A second tick at the same instant must not fire again.
        assert await scheduler.tick(NOW) == []

    @pytest.mark.asyncio
    async def test_disabled_routine_is_skipped(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        routines.create(
            bot_id,
            "暂停",
            {"kind": "interval", "minutes": 30},
            "x",
            enabled=False,
            next_run_at=(NOW - timedelta(minutes=1)).isoformat(),
        )
        fired: list[str] = []

        async def on_fire(item, scheduled_at: str) -> None:
            fired.append(item.id)

        scheduler = Scheduler(routines, on_fire, now=lambda: NOW)
        assert await scheduler.tick(NOW) == []
        assert fired == []

    @pytest.mark.asyncio
    async def test_new_routine_gets_future_slot(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        routine = routines.create(
            bot_id,
            "每天九点",
            {"kind": "daily", "at": "09:00", "tz": "Asia/Shanghai"},
            "x",
        )
        scheduler = Scheduler(routines, _noop, now=lambda: NOW)

        assert await scheduler.tick(NOW) == []
        updated = routines.get(routine.id)
        assert updated is not None
        assert updated.next_run_at is not None
        assert datetime.fromisoformat(updated.next_run_at) > NOW

    @pytest.mark.asyncio
    async def test_past_one_shot_still_fires_once(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        past = (NOW - timedelta(seconds=5)).isoformat()
        routine = routines.create(
            bot_id,
            "补跑一次",
            {"kind": "once", "at": past},
            "x",
        )
        fired: list[str] = []

        async def on_fire(item, scheduled_at: str) -> None:
            fired.append(item.id)

        scheduler = Scheduler(routines, on_fire, now=lambda: NOW)
        assert await scheduler.tick(NOW) == [routine.id]
        await asyncio.sleep(0.05)
        assert fired == [routine.id]

        updated = routines.get(routine.id)
        assert updated is not None
        assert updated.next_run_at is None
        assert await scheduler.tick(NOW) == []

    @pytest.mark.asyncio
    async def test_already_fired_slot_is_not_repeated(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        scheduled = (NOW - timedelta(minutes=1)).isoformat()
        routine = routines.create(
            bot_id,
            "重复",
            {"kind": "interval", "minutes": 30},
            "x",
            next_run_at=scheduled,
        )
        assert routines.record_fire(routine.id, scheduled, "fire_existing") is True

        fired: list[str] = []

        async def on_fire(item, scheduled_at: str) -> None:
            fired.append(item.id)

        scheduler = Scheduler(routines, on_fire, now=lambda: NOW)
        assert await scheduler.tick(NOW) == []
        assert fired == []
        updated = routines.get(routine.id)
        assert updated is not None
        assert updated.next_run_at is not None
        assert datetime.fromisoformat(updated.next_run_at) > NOW


async def _noop(routine, scheduled_at: str) -> None:
    return None


class TestSchedulerLoop:
    @pytest.mark.asyncio
    async def test_start_runs_the_tick_loop(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        routines.create(
            bot_id,
            "loop",
            {"kind": "interval", "minutes": 30},
            "x",
            next_run_at=(NOW - timedelta(minutes=1)).isoformat(),
        )
        fired: list[str] = []

        async def on_fire(item, scheduled_at: str) -> None:
            fired.append(item.id)

        scheduler = Scheduler(routines, on_fire, tick_seconds=0.02, now=lambda: NOW)
        await scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()

        assert len(fired) == 1


class TestRoutineRepository:
    def test_crud(self, env: tuple[RoutineRepository, str]) -> None:
        routines, bot_id = env
        routine = routines.create(
            bot_id,
            "日报",
            {"kind": "daily", "at": "09:00", "tz": "Asia/Shanghai"},
            "写日报",
            target_group_id=None,
        )
        assert routines.get(routine.id) == routine
        assert [item.id for item in routines.list(bot_id=bot_id)] == [routine.id]

        updated = routines.update(routine.id, name="周报", enabled=False)
        assert updated is not None
        assert updated.name == "周报"
        assert updated.enabled is False

        assert routines.delete(routine.id) is True
        assert routines.get(routine.id) is None
