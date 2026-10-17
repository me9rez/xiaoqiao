"""Transport abstraction — writes JSON frames to a stream (stdout).

References:
    hermes tui_gateway/transport.py — StdioTransport
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, TextIO

logger = logging.getLogger(__name__)


class StdioTransport:
    """Writes newline-delimited JSON frames to a text stream.

    The TUI reads these from stdout as a line-delimited JSON-RPC event stream.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream: TextIO = stream or sys.stdout
        self._closed: bool = False

    def write(self, obj: dict[str, Any]) -> bool:
        """Serialize *obj* as JSON and write a newline-delimited frame.

        Returns True on success, False when the stream is closed.
        """
        if self._closed:
            return False
        try:
            line = json.dumps(obj, ensure_ascii=False, default=str)
            self._stream.write(line)
            self._stream.write("\n")
            self._stream.flush()
            return True
        except BrokenPipeError:
            logger.warning("StdioTransport: broken pipe, marking closed")
            self._closed = True
            return False
        except OSError as exc:
            logger.warning("StdioTransport: write error: %s", exc)
            self._closed = True
            return False

    def close(self) -> None:
        """Release the stream (does not close sys.stdout)."""
        self._closed = True
        try:
            self._stream.flush()
        except OSError:
            pass

    @property
    def closed(self) -> bool:
        return self._closed
