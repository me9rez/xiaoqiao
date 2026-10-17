"""Shared channel contracts.

Adapters only translate transport events into ``InboundMessage`` and render
outbound text/files/approval buttons.  No agent logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class InboundMessage:
    bot_id: str
    channel_id: str
    external_chat_id: str
    external_user_id: str
    text: str
    attachments: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send_text(self, chat_id: str, text: str) -> None: ...

    async def send_file(self, chat_id: str, path: str, caption: str = "") -> None: ...
