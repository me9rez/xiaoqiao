"""Single-writer coordination for processes sharing ``~/.xiaoqiao/agent.db``.

The desktop shell and the CLI may run at the same time against the same
database. SQLite in WAL mode copes with that (it serialises writers and gives
readers a consistent snapshot), but *background work* must happen exactly once:
two schedulers would fire every routine twice, and two Telegram adapters would
long-poll the same bot and split updates between them.

There is no portable advisory file lock in the standard library, so the slot is
taken by binding a loopback port. The kernel refuses the second bind, and it
releases automatically when the owning process dies — no stale lock files, no
pid liveness probing, nothing to clean up after a crash.
"""

from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)

#: Loopback port used purely as a process-wide "background work" slot.
SCHEDULER_PORT = 8760


class EngineSlot:
    """Ownership of the background-work slot (scheduler + channel adapters)."""

    def __init__(self, port: int = SCHEDULER_PORT) -> None:
        self._port = port
        self._sock: socket.socket | None = None

    @property
    def owns(self) -> bool:
        """True when this process holds the slot."""
        return self._sock is not None

    def acquire(self) -> bool:
        """Try to take the slot.

        Returns:
            True when this process now owns it (including a repeat call from
            the same object), False when another live engine holds it.
        """
        if self._sock is not None:
            return True
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # No SO_REUSEADDR: a second bind on the same port must fail.
            sock.bind(("127.0.0.1", self._port))
            sock.listen(1)
        except OSError:
            sock.close()
            return False
        self._sock = sock
        logger.info("Background work slot acquired on 127.0.0.1:%d", self._port)
        return True

    def release(self) -> None:
        """Give the slot back (also happens implicitly when the process exits)."""
        if self._sock is None:
            return
        try:
            self._sock.close()
        finally:
            self._sock = None
