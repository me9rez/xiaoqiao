"""Unit tests for the Telegram adapter using a fake HTTP transport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from xiaoqiao.channels.base import InboundMessage
from xiaoqiao.channels.telegram import TelegramAdapter


class FakeTelegram:
    def __init__(self, updates: list[dict[str, Any]] | None = None) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.updates = updates or []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/getUpdates"):
            self.requests.append((path, json.loads(request.content)))
            return httpx.Response(200, json={"ok": True, "result": self.updates})
        if path.endswith("/sendDocument"):
            self.requests.append((path, {"content_type": request.headers.get("content-type", "")}))
            return httpx.Response(200, json={"ok": True, "result": {}})
        body = json.loads(request.content or b"{}")
        self.requests.append((path, body))
        return httpx.Response(200, json={"ok": True, "result": {}})


async def _build(fake: FakeTelegram, **kwargs: Any):
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), base_url="https://tg.test")
    received: list[InboundMessage] = []
    approvals: list[tuple[str, bool, str, str]] = []

    async def on_message(message: InboundMessage) -> None:
        received.append(message)

    async def on_approval(approval_id: str, approved: bool, user_id: str, chat_id: str) -> None:
        approvals.append((approval_id, approved, user_id, chat_id))

    adapter = TelegramAdapter(
        channel_id="ch_1",
        bot_id="bot_1",
        token="T",
        on_message=on_message,
        on_approval=on_approval,
        client=client,
        **kwargs,
    )
    return adapter, client, received, approvals


class TestInbound:
    @pytest.mark.asyncio
    async def test_parses_message_and_advances_offset(self) -> None:
        fake = FakeTelegram(
            updates=[
                {
                    "update_id": 10,
                    "message": {
                        "message_id": 1,
                        "text": "@coder 看一下",
                        "chat": {"id": 42, "type": "private"},
                        "from": {"id": 7},
                        "document": {"file_id": "f1", "file_name": "a.pdf", "file_size": 10},
                    },
                }
            ]
        )
        adapter, client, received, _ = await _build(fake)
        try:
            offset = await adapter.poll_once()
        finally:
            await client.aclose()

        assert offset == 11
        assert len(received) == 1
        assert received[0].text == "@coder 看一下"
        assert received[0].external_chat_id == "42"
        assert received[0].external_user_id == "7"
        assert received[0].attachments[0]["name"] == "a.pdf"

    @pytest.mark.asyncio
    async def test_ignores_empty_text(self) -> None:
        fake = FakeTelegram(
            updates=[
                {"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": 2}, "text": "  "}},
                {"update_id": 2, "message": {"chat": {"id": 1}, "from": {"id": 2}, "photo": [{"file_id": "p"}]}},
            ]
        )
        adapter, client, received, _ = await _build(fake)
        try:
            await adapter.poll_once()
        finally:
            await client.aclose()

        assert received == []


class TestApprovalCallback:
    @pytest.mark.asyncio
    async def test_callback_is_translated(self) -> None:
        fake = FakeTelegram(
            updates=[
                {
                    "update_id": 3,
                    "callback_query": {
                        "id": "cb_1",
                        "data": "ap:ap_9:1",
                        "from": {"id": 7},
                        "message": {"chat": {"id": 42}},
                    },
                }
            ]
        )
        adapter, client, _, approvals = await _build(fake)
        try:
            await adapter.poll_once()
        finally:
            await client.aclose()

        assert approvals == [("ap_9", True, "7", "42")]
        assert any(path.endswith("/answerCallbackQuery") for path, _ in fake.requests)


class TestOutbound:
    @pytest.mark.asyncio
    async def test_send_text_chunks_long_messages(self) -> None:
        fake = FakeTelegram()
        adapter, client, _, _ = await _build(fake)
        try:
            await adapter.send_text("42", "x" * 5000)
        finally:
            await client.aclose()

        sends = [body for path, body in fake.requests if path.endswith("/sendMessage")]
        assert len(sends) == 2
        assert len(sends[0]["text"]) == 4096
        assert sends[0]["chat_id"] == "42"

    @pytest.mark.asyncio
    async def test_send_approval_has_inline_keyboard(self) -> None:
        fake = FakeTelegram()
        adapter, client, _, _ = await _build(fake)
        try:
            await adapter.send_approval("42", approval_id="ap_1", tool="run_command", arguments="{}")
        finally:
            await client.aclose()

        body = next(body for path, body in fake.requests if path.endswith("/sendMessage"))
        buttons = body["reply_markup"]["inline_keyboard"][0]
        assert [button["callback_data"] for button in buttons] == ["ap:ap_1:1", "ap:ap_1:0"]

    @pytest.mark.asyncio
    async def test_send_file(self, tmp_path) -> None:
        fake = FakeTelegram()
        adapter, client, _, _ = await _build(fake)
        file_path = tmp_path / "report.md"
        file_path.write_text("hi", encoding="utf-8")
        try:
            await adapter.send_file("42", str(file_path), caption="report")
        finally:
            await client.aclose()

        assert any(path.endswith("/sendDocument") for path, _ in fake.requests)
