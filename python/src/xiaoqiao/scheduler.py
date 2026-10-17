"""Routine scheduler: a 20-second tick with de-duplicated fires.

The scheduler only decides *when*.  Firing runs an async callback (usually the
gateway submitting a run); missed schedules are caught up once on the next tick,
and ``routine_fires`` makes sure the same planned instant never runs twice.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from xiaoqiao.runtime.routines import Routine, RoutineRepository

logger = logging.getLogger(__name__)

FireCallback = Callable[[Routine, str], Awaitable[None]]

DEFAULT_TICK_SECONDS = 20


def compute_next_run(schedule: dict[str, Any], after: datetime) -> datetime | None:
    """Return the next fire time strictly after ``after`` (UTC), or None."""
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    kind = schedule.get("kind")

    if kind == "interval":
        try:
            minutes = int(schedule.get("minutes", 0))
        except TypeError, ValueError:
            return None
        if minutes <= 0:
            return None
        return after + timedelta(minutes=minutes)

    if kind == "once":
        raw = schedule.get("at")
        if not isinstance(raw, str):
            return None
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment if moment > after else None

    if kind == "daily":
        raw = str(schedule.get("at", ""))
        try:
            hour, minute = (int(part) for part in raw.split(":", 1))
            zone = ZoneInfo(str(schedule.get("tz", "UTC")))
        except ValueError, ZoneInfoNotFoundError:
            return None
        local_now = after.astimezone(zone)
        candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC)

    return None


class Scheduler:
    """Periodic tick that fires due routines exactly once per planned instant."""

    def __init__(
        self,
        routines: RoutineRepository,
        on_fire: FireCallback,
        *,
        tick_seconds: float = DEFAULT_TICK_SECONDS,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._routines = routines
        self._on_fire = on_fire
        self._tick_seconds = tick_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="routine-scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self._tick_seconds)

    async def tick(self, now: datetime | None = None) -> list[str]:
        moment = now or self._now()
        self._initialize(moment)

        fired: list[str] = []
        for routine in self._routines.due(moment.isoformat()):
            scheduled_at = routine.next_run_at
            if scheduled_at is None:
                continue
            fire_id = f"fire_{uuid.uuid4().hex[:12]}"
            if not self._routines.record_fire(routine.id, scheduled_at, fire_id):
                self._advance(routine, moment)
                continue
            next_run = compute_next_run(routine.schedule, moment)
            self._routines.update(
                routine.id,
                next_run_at=next_run.isoformat() if next_run else None,
                last_run_at=scheduled_at,
            )
            fired.append(routine.id)
            task = asyncio.create_task(self._safe_fire(routine, scheduled_at))
            task.add_done_callback(lambda _task: None)
        return fired

    def _initialize(self, moment: datetime) -> None:
        """Give brand-new routines a next fire time; do not run them immediately."""
        for routine in self._routines.list():
            if not routine.enabled or routine.next_run_at is not None:
                continue
            next_run = compute_next_run(routine.schedule, moment)
            if next_run is None and routine.schedule.get("kind") == "once":
                # A one-shot created for an instant that already passed should
                # still run once (catch-up) instead of silently disappearing.
                raw = routine.schedule.get("at")
                if isinstance(raw, str):
                    try:
                        next_run = datetime.fromisoformat(raw)
                    except ValueError:
                        next_run = None
            self._routines.update(
                routine.id,
                next_run_at=next_run.isoformat() if next_run else None,
            )

    def _advance(self, routine: Routine, moment: datetime) -> None:
        next_run = compute_next_run(routine.schedule, moment)
        self._routines.update(
            routine.id,
            next_run_at=next_run.isoformat() if next_run else None,
            last_run_at=routine.next_run_at,
        )

    async def _safe_fire(self, routine: Routine, scheduled_at: str) -> None:
        try:
            await self._on_fire(routine, scheduled_at)
        except Exception:
            logger.exception("Routine %s failed to fire", routine.id)
