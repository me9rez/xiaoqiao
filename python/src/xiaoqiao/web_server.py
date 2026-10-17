"""Static file HTTP server for the web frontend build output.

Runs in a background thread so it does not block the asyncio event loop
used by the WebSocket gateway.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _ReusableAddressHTTPServer(ThreadingHTTPServer):
    """HTTP server that allows quick restart on the same address."""

    allow_reuse_address = True

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class _StaticHandler(SimpleHTTPRequestHandler):
    """Static file handler that suppresses default request logging."""

    def __init__(self, directory: str, *args: Any, **kwargs: Any) -> None:
        self._static_directory = directory
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def end_headers(self) -> None:
        # Avoid caching issues during development.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        # SPA fallback: any non-file request serves index.html.
        translated = super().translate_path(path)
        if not os.path.exists(translated) or os.path.isdir(translated):
            index = os.path.join(self._static_directory, "index.html")
            if os.path.exists(index):
                return index
        return translated


def run_static_server(root: str, host: str = "127.0.0.1", port: int = 8766) -> threading.Thread:
    """Start a static file server in a daemon thread.

    Args:
        root: Directory to serve (e.g. the ``web/dist`` folder).
        host: Interface to bind to.
        port: TCP port to listen on.

    Returns:
        The background thread running the HTTP server.

    Raises:
        FileNotFoundError: If ``root`` does not exist.
        OSError: If the port cannot be bound.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Static root does not exist: {root_path}")

    handler = partial(_StaticHandler, str(root_path))
    server = _ReusableAddressHTTPServer((host, port), handler)

    def _serve() -> None:
        try:
            server.serve_forever()
        except Exception:
            logger.exception("Static server failed")

    thread = threading.Thread(target=_serve, name="xiaoqiao-static-server", daemon=True)
    thread.start()
    logger.info("Static server on http://%s:%d (root=%s)", host, port, root_path)
    print(f"HTTP READY http://{host}:{port}", file=__import__("sys").stderr, flush=True)
    return thread
