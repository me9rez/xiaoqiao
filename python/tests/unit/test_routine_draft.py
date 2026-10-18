"""Tests for turning a finished run into a routine draft ("teach once")."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao.config.schema import Settings
from xiaoqiao.events import ToolCallStartEvent
from xiaoqiao.gateway.ws_server import WsGatewayServer, _summarize_args


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XIAOQIAO_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def server(state_home: Path) -> WsGatewayServer:
    return WsGatewayServer(settings=Settings(), tools=[])


def _bot(server: WsGatewayServer) -> str:
    return server._bots.create("研究员", slug="researcher").id


def _run_with_steps(server: WsGatewayServer) -> str:
    bot_id = _bot(server)
    session = server._sessions_db.get_or_create(bot_id, title="本周竞品摘要").id
    run_id = server._runs.begin(bot_id, session_id=session)
    server._emit(
        ToolCallStartEvent(call_id="c1", name="read_file", arguments='{"path": "docs/竞品.md"}'),
        session_id=session,
        run_id=run_id,
    )
    server._emit(
        ToolCallStartEvent(call_id="c2", name="write_file", arguments='{"path": "docs/摘要.md"}'),
        session_id=session,
        run_id=run_id,
    )
    server._finish_run(run_id, "done")
    return run_id


class TestSummarizeArgs:
    def test_picks_a_readable_field(self) -> None:
        assert _summarize_args('{"path": "docs/a.md", "content": "..."}') == "docs/a.md"

    def test_masks_secret_looking_keys(self) -> None:
        assert _summarize_args('{"api_key": "sk-live-1"}') == "api_key=***"

    def test_non_json_is_truncated(self) -> None:
        assert _summarize_args("not json") == "not json"


class TestRunStepCapture:
    def test_steps_are_persisted_when_the_run_finishes(self, server: WsGatewayServer) -> None:
        run_id = _run_with_steps(server)

        steps = server._runs.steps(run_id)

        assert [step["tool"] for step in steps] == ["read_file", "write_file"]
        assert steps[0]["argsSummary"] == "docs/竞品.md"

    def test_unknown_run_is_rejected(self, server: WsGatewayServer) -> None:
        with pytest.raises(ValueError):
            server._draft_routine_from_run("run_missing")


class TestDraftRoutine:
    def test_draft_carries_steps_name_and_schedule(self, server: WsGatewayServer) -> None:
        run_id = _run_with_steps(server)

        draft = server._draft_routine_from_run(run_id)

        assert draft["runId"] == run_id
        assert draft["name"] == "本周竞品摘要"
        assert draft["hasSteps"] is True
        assert [step["tool"] for step in draft["steps"]] == ["read_file", "write_file"]
        assert draft["schedule"]["kind"] == "daily"
        assert draft["schedule"]["at"] == "09:00"

    def test_draft_without_steps_still_works(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        run_id = server._runs.begin(bot_id)
        server._finish_run(run_id, "done")

        draft = server._draft_routine_from_run(run_id)

        assert draft["hasSteps"] is False
        assert draft["name"]


class TestRoutineSteps:
    def test_prompt_gets_the_recorded_steps(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        routine = server._routines.create(bot_id, "周报", {"kind": "daily", "at": "09:00", "tz": "UTC"}, "写周报")

        server._routines.set_steps(
            routine.id,
            [{"tool": "read_file", "argsSummary": "docs/a.md"}, {"tool": "write_file", "argsSummary": "docs/b.md"}],
        )

        prompt = server._routines.prompt_with_steps(routine)

        assert prompt.startswith("写周报")
        assert "1. read_file（docs/a.md）" in prompt
        assert "2. write_file（docs/b.md）" in prompt

    def test_prompt_without_steps_is_untouched(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        routine = server._routines.create(bot_id, "周报", {"kind": "daily", "at": "09:00", "tz": "UTC"}, "写周报")

        assert server._routines.prompt_with_steps(routine) == "写周报"

    def test_payload_exposes_steps(self, server: WsGatewayServer) -> None:
        bot_id = _bot(server)
        routine = server._routines.create(bot_id, "周报", {"kind": "daily", "at": "09:00", "tz": "UTC"}, "写周报")
        server._routines.set_steps(routine.id, [{"tool": "read_file", "argsSummary": "a"}])

        payload = server._routine_payload(routine)

        assert payload["steps"] == [{"tool": "read_file", "argsSummary": "a"}]
