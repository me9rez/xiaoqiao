"""Two engines must not both run background work (desktop-plan R8).

The desktop shell and the CLI share one database. SQLite copes; the scheduler
and the channel adapters do not — they would fire every routine twice.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

from xiaoqiao.gateway import ws_server as ws_module
from xiaoqiao.gateway.ws_server import WsGatewayServer
from xiaoqiao.runtime.instance_lock import EngineSlot

TEST_PORT = 18760


class TestEngineSlot:
    def test_second_slot_cannot_acquire(self) -> None:
        first = EngineSlot(TEST_PORT)
        second = EngineSlot(TEST_PORT)
        try:
            assert first.acquire() is True
            assert first.owns is True
            assert second.acquire() is False
            assert second.owns is False
        finally:
            first.release()
            second.release()

    def test_slot_is_reusable_after_release(self) -> None:
        first = EngineSlot(TEST_PORT)
        second = EngineSlot(TEST_PORT)
        assert first.acquire() is True
        first.release()
        try:
            assert second.acquire() is True
        finally:
            second.release()

    def test_acquire_is_idempotent(self) -> None:
        slot = EngineSlot(TEST_PORT)
        try:
            assert slot.acquire() is True
            assert slot.acquire() is True
            assert slot.owns is True
        finally:
            slot.release()
        assert slot.owns is False


class TestPassiveMode:
    async def test_second_engine_starts_passive(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(ws_module, "SCHEDULER_PORT", TEST_PORT)
        # Occupy the slot the way another live engine would.
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", TEST_PORT))
        blocker.listen(1)
        server = WsGatewayServer(port=0, db_path=tmp_path / "agent.db")
        task = asyncio.create_task(server.run_forever())
        try:
            for _ in range(250):
                if server.port:
                    break
                await asyncio.sleep(0.02)
            assert server.port > 0
            assert server.passive is True
            # The scheduler never started, so routines cannot double-fire.
            assert server._scheduler._task is None
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            blocker.close()

    async def test_first_engine_owns_background_work(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(ws_module, "SCHEDULER_PORT", TEST_PORT)
        server = WsGatewayServer(port=0, db_path=tmp_path / "agent.db")
        task = asyncio.create_task(server.run_forever())
        try:
            for _ in range(250):
                if server.port:
                    break
                await asyncio.sleep(0.02)
            assert server.passive is False
            assert server._scheduler._task is not None
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # The slot must be free again for the next engine.
        reuse = EngineSlot(TEST_PORT)
        try:
            assert reuse.acquire() is True
        finally:
            reuse.release()
