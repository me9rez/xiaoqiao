"""Telegram adapter: long polling in, text/files/approval buttons out.

The adapter is deliberately thin.  It normalises updates into
``InboundMessage`` and hands them to a callback owned by the runtime; it never
decides which bot should answer or whether an approval is allowed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from xiaoqiao.channels.base import InboundMessage

logger = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096


class TelegramAdapter:
    def __init__(
        self,
        *,
        channel_id: str,
        bot_id: str,
        token: str,
        on_message: Callable[[InboundMessage], Awaitable[None]],
        on_approval: Callable[[str, bool, str, str], Awaitable[None]] | None = None,
        api_base: str = "https://api.telegram.org",
        client: httpx.AsyncClient | None = None,
        poll_timeout: int = 25,
    ) -> None:
        self.channel_id = channel_id
        self.bot_id = bot_id
        self._token = token
        self._on_message = on_message
        self._on_approval = on_approval
        self._client = client or httpx.AsyncClient(base_url=api_base, timeout=40)
        self._owns_client = client is None
        self._poll_timeout = poll_timeout
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._loop(), name=f"telegram:{self.channel_id}")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._owns_client:
            await self._client.aclose()

    async def _loop(self) -> None:
        offset: int | None = None
        while not self._stopped.is_set():
            try:
                offset = await self.poll_once(offset)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram poll failed (channel %s)", self.channel_id)
                await asyncio.sleep(2)
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=0.5)

    # ── inbound ──────────────────────────────────────────────────

    async def poll_once(self, offset: int | None = None) -> int | None:
        payload: dict[str, Any] = {
            "timeout": 0,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        response = await self._client.post(f"/bot{self._token}/getUpdates", json=payload)
        response.raise_for_status()
        updates = response.json().get("result", [])
        next_offset = offset
        for update in updates:
            next_offset = max(next_offset or 0, int(update.get("update_id", 0)) + 1)
            await self._handle_update(update)
        return next_offset

    async def _handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._handle_callback(update["callback_query"])
            return
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        text = message.get("text") or message.get("caption") or ""
        if not text.strip():
            return
        chat = message.get("chat", {})
        sender = message.get("from", {})
        inbound = InboundMessage(
            bot_id=self.bot_id,
            channel_id=self.channel_id,
            external_chat_id=str(chat.get("id", "")),
            external_user_id=str(sender.get("id", "")),
            text=text,
            attachments=self._attachments(message),
            raw=update,
        )
        await self._on_message(inbound)

    @staticmethod
    def _attachments(message: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        found: list[dict[str, Any]] = []
        if "document" in message:
            document = message["document"]
            found.append(
                {
                    "kind": "document",
                    "file_id": document.get("file_id"),
                    "name": document.get("file_name"),
                    "size": document.get("file_size"),
                }
            )
        if isinstance(message.get("photo"), list) and message["photo"]:
            largest = message["photo"][-1]
            found.append({"kind": "photo", "file_id": largest.get("file_id")})
        if "audio" in message:
            found.append({"kind": "audio", "file_id": message["audio"].get("file_id")})
        return tuple(found)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        data = str(callback.get("data", ""))
        parts = data.split(":")
        sender = callback.get("from", {})
        chat = (callback.get("message") or {}).get("chat", {})
        await self.answer_callback(str(callback.get("id", "")))
        if len(parts) != 3 or parts[0] != "ap" or self._on_approval is None:
            return
        approval_id, verdict = parts[1], parts[2]
        await self._on_approval(
            approval_id,
            verdict == "1",
            str(sender.get("id", "")),
            str(chat.get("id", "")),
        )

    # ── outbound ─────────────────────────────────────────────────

    async def send_text(self, chat_id: str, text: str) -> None:
        for chunk in self._chunks(text):
            response = await self._client.post(
                f"/bot{self._token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
            )
            response.raise_for_status()

    async def send_file(self, chat_id: str, path: str, caption: str = "") -> None:
        from pathlib import Path

        file_path = Path(path)
        with file_path.open("rb") as handle:
            response = await self._client.post(
                f"/bot{self._token}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (file_path.name, handle)},
            )
        response.raise_for_status()

    async def send_approval(
        self,
        chat_id: str,
        *,
        approval_id: str,
        tool: str,
        arguments: str,
    ) -> None:
        text = f"需要你确认：{tool}\n{arguments}"[:TELEGRAM_LIMIT]
        response = await self._client.post(
            f"/bot{self._token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "批准", "callback_data": f"ap:{approval_id}:1"},
                            {"text": "拒绝", "callback_data": f"ap:{approval_id}:0"},
                        ]
                    ]
                },
            },
        )
        response.raise_for_status()

    async def answer_callback(self, callback_id: str) -> None:
        if not callback_id:
            return
        with contextlib.suppress(httpx.HTTPError):
            await self._client.post(
                f"/bot{self._token}/answerCallbackQuery",
                json={"callback_query_id": callback_id},
            )

    @staticmethod
    def _chunks(text: str) -> list[str]:
        if len(text) <= TELEGRAM_LIMIT:
            return [text]
        return [text[index : index + TELEGRAM_LIMIT] for index in range(0, len(text), TELEGRAM_LIMIT)]
