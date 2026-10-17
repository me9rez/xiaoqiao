"""Integration test for the gateway's group prompt wiring (no LLM involved)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from xiaoqiao.agent_runtime import PendingApproval
from xiaoqiao.gateway.ws_server import WsGatewayServer
from xiaoqiao.settings import Settings


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WsGatewayServer:
    # Keep the gateway's repositories inside the temp directory.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return WsGatewayServer(settings=Settings(), tools=[])


class TestGroupPromptWiring:
    @pytest.mark.asyncio
    async def test_routes_and_persists(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        watch = server._bots.create("盯盘", slug="watch")
        group = server._groups.create(
            "Daily",
            [coder.id, watch.id],
            default_bot_id=watch.id,
        )

        async def fake_execute(bot, session, messages, group_id, *, trigger="group") -> str:
            return f"{bot.name} 收到"

        server._execute_group_bot = fake_execute  # type: ignore[method-assign]

        await server._handle_group_prompt(group.id, "@watch 查行情")

        messages = server._group_messages.list(group.id)
        assert [(m.author_type, m.text) for m in messages] == [
            ("user", "@watch 查行情"),
            ("bot", "盯盘 收到"),
        ]
        sessions = server._sessions_db.list(group_id=group.id)
        assert len(sessions) == 1
        assert sessions[0].last_seen_seq == messages[-1].seq

    def test_scan_artifacts_indexes_new_files(self, server: WsGatewayServer, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        bot = server._bots.create("Writer", workspace=str(workspace))
        started = datetime.now(UTC)
        (workspace / "out.md").write_text("hello", encoding="utf-8")

        server._scan_artifacts(bot, started)

        artifacts = server._artifacts.list(bot_id=bot.id)
        assert [artifact.path for artifact in artifacts] == ["out.md"]
        assert artifacts[0].mime == "text/markdown"

    @pytest.mark.asyncio
    async def test_routine_posts_into_its_group(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        group = server._groups.create("Daily", [coder.id])
        routine = server._routines.create(
            coder.id,
            "日报",
            {"kind": "interval", "minutes": 30},
            "写一条日报",
            target_group_id=group.id,
        )

        async def fake_execute(bot, session, messages, group_id, *, trigger="group") -> str:
            return "日报写好了"

        server._execute_group_bot = fake_execute  # type: ignore[method-assign]

        await server._fire_routine(routine, "2026-10-18T01:00:00+00:00")

        messages = server._group_messages.list(group.id)
        assert [message.text for message in messages] == ["写一条日报", "日报写好了"]
        assert messages[0].author_type == "user"

    @pytest.mark.asyncio
    async def test_handoff_advances_two_sessions(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        watch = server._bots.create("盯盘", slug="watch")
        group = server._groups.create(
            "Daily",
            [coder.id, watch.id],
            default_bot_id=watch.id,
            settings={"maxHops": 2},
        )

        async def fake_execute(bot, session, messages, group_id, *, trigger="group") -> str:
            if bot.id == watch.id:
                return "@coder 整理一下"
            return "整理完了"

        server._execute_group_bot = fake_execute  # type: ignore[method-assign]

        await server._handle_group_prompt(group.id, "@watch 查行情")

        messages = server._group_messages.list(group.id)
        assert [m.text for m in messages] == ["@watch 查行情", "@coder 整理一下", "整理完了"]
        sessions = server._sessions_db.list(group_id=group.id)
        assert len(sessions) == 2


class FakeAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.files: list[tuple[str, str, str]] = []

    async def send_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    async def send_file(self, chat_id: str, path: str, caption: str = "") -> None:
        self.files.append((chat_id, path, caption))


class TestRunRecords:
    def test_preview_prompt_includes_persona(self, server: WsGatewayServer) -> None:
        bot = server._bots.create("Coder", slug="coder", persona="你说话很简短。")

        prompt = server.preview_prompt(bot.id)

        assert "## 人格：Coder" in prompt
        assert "你说话很简短。" in prompt

    @pytest.mark.asyncio
    async def test_channel_probe_reports_missing_token(self, server: WsGatewayServer) -> None:
        bot = server._bots.create("Coder", slug="coder")
        channel = server._channels.create(bot.id, "telegram", {"groupId": "grp_1"})

        result = await server.test_channel(channel.id)

        assert result == {"ok": False, "error": "缺少 Bot Token"}

    @pytest.mark.asyncio
    async def test_channel_probe_rejects_unknown_kind(self, server: WsGatewayServer) -> None:
        bot = server._bots.create("Coder", slug="coder")
        channel = server._channels.create(bot.id, "slack", {"token": "T"})

        result = await server.test_channel(channel.id)

        assert result["ok"] is False

    def test_budget_gate_blocks_when_exceeded(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        server._settings = Settings(daily_token_budget=100)
        server._usage.record(coder.id, "m", input_tokens=200)

        assert server._budget_error() is not None

        server._usage.record(coder.id, "m", input_tokens=1)
        server._settings = Settings(daily_token_budget=10_000)
        assert server._budget_error() is None

    def test_session_memory_is_recorded(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        messages = [
            {"role": "user", "contents": [{"type": "text", "text": "帮我整理日报"}]},
            {"role": "assistant", "contents": [{"type": "text", "text": "好的"}]},
        ]

        server._record_session_memory(coder.id, "ses_1", messages)
        server._record_session_memory(coder.id, "ses_1", messages)

        notes = server._memory.recent_notes(coder.id)
        assert len(notes) == 1
        assert "帮我整理日报" in notes[0].text

    def test_tool_whitelist_filters_tools(self, server: WsGatewayServer) -> None:
        from types import SimpleNamespace

        server._tools = [SimpleNamespace(name="read_file"), SimpleNamespace(name="run_command")]
        bot = server._bots.create("Coder", slug="coder")

        assert len(server._tools_for(bot)) == 2

        limited = server._bots.update(bot.id, tools=["read_file"])
        assert limited is not None
        assert [tool.name for tool in server._tools_for(limited)] == ["read_file"]

    def test_record_approval_reuses_the_run(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        run_id = server._runs.begin(coder.id, trigger="web")
        pending = PendingApproval(
            call_id="call_1",
            name="run_command",
            arguments="{}",
            request=cast(Any, None),
        )

        approval = server._record_approval(pending, coder, run_id=run_id)

        assert approval.run_id == run_id
        assert [item.id for item in server._runs.list(bot_id=coder.id)] == [run_id]


class TestChannelRouting:
    @pytest.mark.asyncio
    async def test_artifacts_are_sent_to_the_bound_channel(self, server: WsGatewayServer, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        bot = server._bots.create("Writer", workspace=str(workspace))
        group = server._groups.create("Daily", [bot.id])
        channel = server._channels.create(
            bot.id,
            "telegram",
            {"token": "T", "groupId": group.id, "chatId": "42"},
        )
        adapter = FakeAdapter()
        server._adapters[channel.id] = adapter  # type: ignore[assignment]

        started = datetime.now(UTC)
        (workspace / "report.md").write_text("hi", encoding="utf-8")
        server._scan_artifacts(bot, started, group_id=group.id)
        await asyncio.sleep(0.01)

        assert adapter.files == [("42", str(workspace / "report.md"), "report.md")]

    @pytest.mark.asyncio
    async def test_inbound_message_runs_group_and_replies(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        group = server._groups.create("Daily", [coder.id])
        channel = server._channels.create(
            coder.id,
            "telegram",
            {"token": "T", "groupId": group.id, "chatId": "42"},
        )
        adapter = FakeAdapter()
        server._adapters[channel.id] = adapter  # type: ignore[assignment]

        async def fake_execute(bot, session, messages, group_id, *, trigger="group") -> str:
            return "收到"

        server._execute_group_bot = fake_execute  # type: ignore[method-assign]

        from xiaoqiao.channels.base import InboundMessage

        inbound = InboundMessage(
            bot_id=coder.id,
            channel_id=channel.id,
            external_chat_id="42",
            external_user_id="7",
            text="@coder 你好",
        )
        await server._on_channel_message(channel, inbound)

        assert [m.text for m in server._group_messages.list(group.id)] == ["@coder 你好", "收到"]
        assert adapter.sent == [("42", "收到")]

    @pytest.mark.asyncio
    async def test_ignores_unexpected_chat(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        group = server._groups.create("Daily", [coder.id])
        channel = server._channels.create(
            coder.id,
            "telegram",
            {"token": "T", "groupId": group.id, "chatId": "42"},
        )

        from xiaoqiao.channels.base import InboundMessage

        inbound = InboundMessage(
            bot_id=coder.id,
            channel_id=channel.id,
            external_chat_id="999",
            external_user_id="7",
            text="hi",
        )
        await server._on_channel_message(channel, inbound)

        assert server._group_messages.list(group.id) == []

    @pytest.mark.asyncio
    async def test_approval_callback_resolves(self, server: WsGatewayServer) -> None:
        coder = server._bots.create("Coder", slug="coder")
        run_id = server._approvals.create_run(coder.id)
        approval = server._approvals.create(run_id, "call_1", coder.id, "run_command", "{}")

        await server._on_channel_approval(approval.id, True, "7", "42")

        resolved = server._approvals.get(approval.id)
        assert resolved is not None
        assert resolved.status == "approved"
