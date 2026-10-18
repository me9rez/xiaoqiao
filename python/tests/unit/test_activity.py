"""Tests for the server-side activity snapshot ("what is every bot doing")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.config.schema import Settings
from xiaoqiao.gateway.ws_server import WsGatewayServer
from xiaoqiao.runtime.runs import RunRepository


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def server(state_home: Path) -> WsGatewayServer:
    return WsGatewayServer(settings=Settings(), tools=[])


def _bot(server: WsGatewayServer, name: str = "Coder") -> str:
    return server._bots.create(name, slug=name.lower()).id


def _session(server: WsGatewayServer, bot_id: str, title: str = "") -> str:
    return server._sessions_db.get_or_create(bot_id, title=title).id


class TestRunRepositoryHook:
    def test_changes_notify_the_owner(self, state_home: Path) -> None:
        calls: list[str] = []
        runs = RunRepository(on_change=lambda: calls.append("x"))
        bot_id = BotRepository().create("Coder", slug="coder").id

        run_id = runs.begin(bot_id)
        runs.set_status(run_id, "waiting_approval")
        runs.finish(run_id, "done")

        assert len(calls) == 3

    def test_a_failing_hook_does_not_break_the_run(self, state_home: Path) -> None:
        def boom() -> None:
            raise RuntimeError("hook exploded")

        runs = RunRepository(on_change=boom)
        bot_id = BotRepository().create("Coder", slug="coder").id

        run_id = runs.begin(bot_id)
        runs.finish(run_id, "done")

        assert runs.get(run_id).status == "done"  # type: ignore[union-attr]


class TestActivitySnapshot:
    def test_idle_when_nothing_is_running(self, server: WsGatewayServer) -> None:
        _bot(server)

        snapshot = server._activity_snapshot()

        assert [entry["state"] for entry in snapshot["bots"]] == ["idle"]
        assert snapshot["pendingApprovals"] == 0
        assert "generatedAt" in snapshot

    def test_working_while_a_run_is_open(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        session = _session(server, bot_id)

        run_id = server._runs.begin(bot_id, session_id=session)
        entry = server._activity_snapshot()["bots"][0]

        assert entry["state"] == "working"
        assert entry["runId"] == run_id
        assert entry["sessionId"] == session

    def test_needs_you_outranks_working(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        session = _session(server, bot_id)
        waiting = server._runs.begin(bot_id, session_id=session)
        server._runs.begin(bot_id, session_id=session)
        server._runs.set_status(waiting, "waiting_approval")

        entry = server._activity_snapshot()["bots"][0]

        assert entry["state"] == "needs_you"
        assert entry["runId"] == waiting

    def test_current_tool_is_reported(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        session = _session(server, bot_id)
        run_id = server._runs.begin(bot_id, session_id=session)
        server._run_tool[run_id] = "write_file"

        entry = server._activity_snapshot()["bots"][0]

        assert entry["currentTool"] == "write_file"

    def test_finished_run_is_idle_with_a_summary(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        session = _session(server, bot_id)
        run_id = server._runs.begin(bot_id, session_id=session)
        server._runs.finish(run_id, "done")

        entry = server._activity_snapshot()["bots"][0]

        assert entry["state"] == "idle"
        assert entry["lastFinished"]["runId"] == run_id
        assert entry["lastFinished"]["status"] == "done"

    def test_recent_failure_shows_error_then_ages_out(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        session = _session(server, bot_id)
        run_id = server._runs.begin(bot_id, session_id=session)
        server._runs.finish(run_id, "failed", error="boom")

        assert server._activity_snapshot()["bots"][0]["state"] == "error"

        stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        with server._runs._connect() as conn:
            conn.execute("UPDATE runs SET ended_at = ? WHERE id = ?", (stale, run_id))

        assert server._activity_snapshot()["bots"][0]["state"] == "idle"

    def test_pending_approvals_are_counted(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        session = _session(server, bot_id)
        run_id = server._runs.begin(bot_id, session_id=session)
        server._approvals.create(run_id, "call-1", bot_id, "run_command", "{}")

        assert server._activity_snapshot()["pendingApprovals"] == 1
