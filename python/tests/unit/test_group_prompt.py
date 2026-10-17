"""Integration test for the gateway's group prompt wiring (no LLM involved)."""

from __future__ import annotations

from pathlib import Path

import pytest

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

        async def fake_execute(bot, session, messages, group_id) -> str:
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

        async def fake_execute(bot, session, messages, group_id) -> str:
            if bot.id == watch.id:
                return "@coder 整理一下"
            return "整理完了"

        server._execute_group_bot = fake_execute  # type: ignore[method-assign]

        await server._handle_group_prompt(group.id, "@watch 查行情")

        messages = server._group_messages.list(group.id)
        assert [m.text for m in messages] == ["@watch 查行情", "@coder 整理一下", "整理完了"]
        sessions = server._sessions_db.list(group_id=group.id)
        assert len(sessions) == 2
