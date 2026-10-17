"""Unit tests for record-only run persistence used by the gateway."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.groups import GroupRepository
from xiaoqiao.runtime.runs import RunRepository


@pytest.fixture
def env(tmp_path: Path) -> tuple[RunRepository, str, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    group = GroupRepository(db).create("Daily", [bot.id])
    return RunRepository(db), bot.id, group.id


class TestRunRepository:
    def test_begin_and_finish(self, env: tuple[RunRepository, str, str]) -> None:
        runs, bot_id, group_id = env

        run_id = runs.begin(bot_id, group_id=group_id, trigger="group")
        record = runs.get(run_id)

        assert record is not None
        assert record.status == "running"
        assert record.group_id == group_id
        assert record.trigger == "group"

        runs.finish(run_id, "done")
        finished = runs.get(run_id)
        assert finished is not None
        assert finished.status == "done"

    def test_failure_keeps_error(self, env: tuple[RunRepository, str, str]) -> None:
        runs, bot_id, _ = env
        run_id = runs.begin(bot_id, trigger="web")

        runs.finish(run_id, "failed", error="boom")

        record = runs.get(run_id)
        assert record is not None
        assert record.status == "failed"
        assert record.error == "boom"

    def test_status_can_be_parked_for_approval(self, env: tuple[RunRepository, str, str]) -> None:
        runs, bot_id, _ = env
        run_id = runs.begin(bot_id, trigger="web")

        runs.set_status(run_id, "waiting_approval")

        record = runs.get(run_id)
        assert record is not None
        assert record.status == "waiting_approval"

    def test_list_filters(self, env: tuple[RunRepository, str, str]) -> None:
        runs, bot_id, group_id = env
        first = runs.begin(bot_id, group_id=group_id, trigger="group")
        second = runs.begin(bot_id, trigger="routine")
        runs.finish(second, "done")

        assert {item.id for item in runs.list(bot_id=bot_id)} == {first, second}
        assert [item.id for item in runs.list(group_id=group_id)] == [first]
        assert [item.id for item in runs.list(status="done")] == [second]
