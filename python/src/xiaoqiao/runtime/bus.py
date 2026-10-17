"""In-process event bus for run-scoped events.

Gateways and channel adapters subscribe here instead of reaching into the
runtime.  Handlers are synchronous; async consumers should enqueue internally.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[["RuntimeEvent"], None]


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    run_id: str | None = None
    bot_id: str | None = None
    session_id: str | None = None
    group_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Minimal publish/subscribe bus with per-event-type subscriptions."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._all: list[Handler] = []

    def subscribe(self, handler: Handler, event_type: str | None = None) -> Callable[[], None]:
        """Subscribe to one event type (or all when omitted); returns an unsubscribe."""
        if event_type is None:
            self._all.append(handler)

            def _remove_all() -> None:
                if handler in self._all:
                    self._all.remove(handler)

            return _remove_all
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(handler)

        def _remove() -> None:
            if handler in handlers:
                handlers.remove(handler)

        return _remove

    def publish(self, event: RuntimeEvent) -> None:
        for handler in list(self._handlers.get(event.type, [])):
            self._safe_call(handler, event)
        for handler in list(self._all):
            self._safe_call(handler, event)

    @staticmethod
    def _safe_call(handler: Handler, event: RuntimeEvent) -> None:
        try:
            handler(event)
        except Exception:
            logger.exception("Runtime event handler failed for %s", event.type)
