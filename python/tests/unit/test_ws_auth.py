"""Desktop-shell contract for the WebSocket gateway.

The desktop shell spawns the engine with ``--desktop``: an OS-assigned port and
a token handshake. These tests pin that behaviour down without a real window.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from xiaoqiao.gateway.ws_server import WsGatewayServer

TOKEN = "s3cret-token"


async def _start(tmp_path: Path, token: str | None) -> tuple[int, asyncio.Task[None]]:
    """Start a gateway on port 0; return the bound port and the server task."""
    server = WsGatewayServer(port=0, auth_token=token, db_path=tmp_path / "agent.db")
    task = asyncio.create_task(server.run_forever())
    for _ in range(250):
        if server.port:
            return server.port, task
        await asyncio.sleep(0.02)
    task.cancel()
    raise AssertionError("gateway never bound a port")


async def _stop(task: asyncio.Task[None]) -> None:
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _recv(ws) -> dict:  # type: ignore[no-untyped-def]
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))


class TestPortBinding:
    async def test_port_zero_gets_an_os_assigned_port(self, tmp_path: Path) -> None:
        port, task = await _start(tmp_path, None)
        try:
            assert port > 0
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                assert (await _recv(ws))["type"] == "ready"
        finally:
            await _stop(task)

    async def test_without_token_ready_arrives_immediately(self, tmp_path: Path) -> None:
        """Browser mode (no --desktop) keeps working exactly as before."""
        port, task = await _start(tmp_path, None)
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                ready = await _recv(ws)
                assert ready["type"] == "ready"
                assert "workspace" in ready
                await ws.send(json.dumps({"id": "1", "method": "getSettings", "params": {}}))
                response = await _recv(ws)
                assert response["id"] == "1"
                assert "result" in response
        finally:
            await _stop(task)


class TestTokenHandshake:
    async def test_method_before_auth_is_rejected(self, tmp_path: Path) -> None:
        port, task = await _start(tmp_path, TOKEN)
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"id": "1", "method": "getSettings", "params": {}}))
                message = await _recv(ws)
                assert message["type"] == "rpc_response"
                assert message["error"]["message"] == "unauthorized"
                with pytest.raises(ConnectionClosed) as closed:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                rcvd = getattr(closed.value, "rcvd", None)
                assert rcvd is not None and rcvd.code == 4401
        finally:
            await _stop(task)

    async def test_wrong_token_is_rejected(self, tmp_path: Path) -> None:
        port, task = await _start(tmp_path, TOKEN)
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"id": "a", "method": "auth", "params": {"token": "nope"}}))
                message = await _recv(ws)
                assert message["error"]["message"] == "unauthorized"
        finally:
            await _stop(task)

    async def test_correct_token_unlocks_ready_and_methods(self, tmp_path: Path) -> None:
        port, task = await _start(tmp_path, TOKEN)
        try:
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                # Nothing is announced before the handshake.
                await ws.send(json.dumps({"id": "a", "method": "auth", "params": {"token": TOKEN}}))
                ack = await _recv(ws)
                assert ack["id"] == "a"
                assert ack["result"] == {"ok": True}
                assert (await _recv(ws))["type"] == "ready"

                await ws.send(json.dumps({"id": "b", "method": "getSettings", "params": {}}))
                response = await _recv(ws)
                assert response["id"] == "b"
                assert "result" in response
        finally:
            await _stop(task)


class TestShutdown:
    async def test_shutdown_rpc_ends_the_gateway(self, tmp_path: Path) -> None:
        port, task = await _start(tmp_path, None)
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            await _recv(ws)  # ready
            await ws.send(json.dumps({"id": "bye", "method": "shutdown", "params": {}}))
            ack = await _recv(ws)
            assert ack["result"] == {"ok": True}
        await asyncio.wait_for(task, timeout=5)
        assert task.done()
