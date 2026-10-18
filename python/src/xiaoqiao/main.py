"""Entry point for the 小巧 gateway.

Configuration is loaded from ``~/.xiaoqiao/config.toml`` (a legacy
``settings.json`` is migrated on first load).
CLI flags and environment variables override file values.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from importlib import resources
from pathlib import Path

from xiaoqiao.mcp import create_mcp_tools, format_mcp_tools_for_prompt
from xiaoqiao.settings import (
    Settings,
    build_client,
    effective_effort,
)
from xiaoqiao.settings import load as load_settings
from xiaoqiao.skills import create_skills_provider
from xiaoqiao.tools.coding_tools import create_coding_tools
from xiaoqiao.web_server import run_static_server

logger = logging.getLogger(__name__)


def _default_web_root() -> str:
    """Return the bundled web frontend directory, falling back to the repo layout in dev.

    When installed as a wheel, the frontend is shipped under ``xiaoqiao/web_dist``
    via hatchling force-include. During development it falls back to the repository's
    ``web/dist`` directory.
    """
    try:
        root = resources.files("xiaoqiao") / "web_dist"
        if root.is_dir():
            return str(root)
    except Exception:
        pass
    return str(Path(__file__).resolve().parents[3] / "web" / "dist")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="小巧（Xiaoqiao）gateway")
    parser.add_argument("--log-level", default="WARNING", help="Logging level")
    parser.add_argument("--test", nargs="*", default=None, help="Run one prompt in CLI test mode")
    parser.add_argument("--model", default=None, help="Override model (default: config.toml)")
    parser.add_argument("--base-url", default=None, help="Override base URL (default: config.toml)")
    parser.add_argument("--thinking-level", default=None, help="Thinking level: off/low/medium/high")
    parser.add_argument("--ws-port", type=int, default=None, help="WebSocket port (WS mode instead of stdio)")
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="Desktop-shell mode: WebSocket only, no static server, no port freeing",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Require this token as the first handshake message (default: env XIAOQIAO_TOKEN)",
    )
    parser.add_argument(
        "--exit-on-stdin-eof",
        action="store_true",
        help="Exit when the parent closes stdin; the desktop shell keeps it open for its lifetime",
    )
    parser.add_argument(
        "--ready-file",
        default=None,
        help='Write {"url", "pid"} here once listening (the shell reads it; a windowed build has no stderr)',
    )
    parser.add_argument("--web", action="store_true", help="Serve the web frontend static files")
    parser.add_argument("--web-port", type=int, default=8766, help="HTTP port for the web static server")
    parser.add_argument("--web-root", default=_default_web_root(), help="Directory to serve as the web frontend")
    return parser.parse_args(argv)


def _free_port(port: int) -> None:
    """Try to terminate any process listening on the given local port (Windows)."""
    if sys.platform != "win32":
        return
    logger.info("Freeing port %d if occupied", port)
    # PowerShell approach (preferred on Windows 8+/10+)
    ps_cmd = (
        f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
        f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    # Fallback to netstat + taskkill
    try:
        ns = subprocess.run(
            f"netstat -ano | findstr :{port}",
            capture_output=True,
            text=True,
            shell=True,
            check=False,
        )
        for line in ns.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    text=True,
                    check=False,
                )
    except Exception:
        pass


def _merge_settings(args: argparse.Namespace) -> Settings:
    """Load settings file, then apply CLI overrides."""
    s = load_settings()
    if args.model:
        s.default_model = args.model
    if args.base_url:
        provider = s.provider(s.default_model)
        if provider is not None:
            provider.base_url = args.base_url
    return s


def _build_client(settings: Settings, model: str | None = None) -> object:
    """Create the LLM client from the selected provider/model."""
    return build_client(settings, model)


async def _run_test_mode(prompt: str, settings: Settings) -> None:
    """Run one prompt in CLI test mode, printing events to stderr.

    Exercises the same runtime the gateways use, so this is a real integration
    check of the harness path rather than a separate code path.
    """
    from xiaoqiao.agent_runtime import AgentRuntime
    from xiaoqiao.framework_session import get_or_create_framework_session, save_framework_session
    from xiaoqiao.system_prompt import (
        BuildSystemPromptOptions,
        build_system_prompt,
        discover_project_context,
    )

    client = _build_client(settings)
    tools = create_coding_tools(approval_config=settings.approval_config())
    skill_provider = create_skills_provider()
    try:
        mcp_tools = create_mcp_tools()
        mcp_tools_prompt = format_mcp_tools_for_prompt(mcp_tools)
    except Exception as exc:
        logger.warning("MCP tools unavailable in test mode: %s", exc)
        mcp_tools = []
        mcp_tools_prompt = ""
    ctx = discover_project_context()
    sys_prompt = build_system_prompt(
        BuildSystemPromptOptions(
            project_context=ctx,
            mcp_tools_prompt=mcp_tools_prompt,
            tool_approval=settings.approval_config(),
        )
    )

    def on_event(event: object) -> None:
        line = json.dumps(
            {
                "type": type(event).__name__,
                **{k: v for k, v in vars(event).items() if v is not None and v != "" and k != "type"},
            },
            ensure_ascii=False,
            default=str,
        )
        print(line, file=sys.stderr, flush=True)

    print(f"User: {prompt}", file=sys.stderr)
    lvl = effective_effort(settings)
    agent_session = get_or_create_framework_session("test-mode")

    runtime = AgentRuntime(
        client=client,
        tools=tools,
        session=agent_session,
        instructions=sys_prompt,
        on_event=on_event,
        settings=settings,
        thinking_level=lvl,
        skill_provider=skill_provider,
        mcp_tools=mcp_tools,
    )

    try:
        outcome = await runtime.run_turn(prompt, on_event)
        if outcome.pending_approval is not None:
            pending = outcome.pending_approval
            print(
                f"PENDING_APPROVAL: {pending.name}({pending.arguments})",
                file=sys.stderr,
                flush=True,
            )
            print(
                f"SESSION_BEFORE_RESUME: {agent_session.to_dict()}",
                file=sys.stderr,
                flush=True,
            )
            # Auto-approve in CLI test mode so the run can complete unattended.
            outcome = await runtime.resolve_approval(pending.call_id, True, on_event)
            if outcome.pending_approval is not None:
                print(
                    f"PENDING_APPROVAL: {outcome.pending_approval.name}({outcome.pending_approval.arguments})",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(f"Final: {outcome.text}", file=sys.stderr)
        else:
            print(f"Final: {outcome.text}", file=sys.stderr)
    finally:
        print(
            f"SESSION_AFTER: {agent_session.to_dict()}",
            file=sys.stderr,
            flush=True,
        )
        save_framework_session(agent_session)


class _StreamToLogger:
    def __init__(self) -> None:
        self._buf: list[str] = []

    def write(self, text: str) -> None:
        self._buf.append(text)
        if "\n" in text:
            for line in "".join(self._buf).splitlines(keepends=True):
                logger.debug("stdout guard: %s", line.rstrip())
            self._buf.clear()

    def flush(self) -> None:
        pass


def _watch_stdin_eof(server: object) -> None:
    """Stop the engine when the parent closes our stdin.

    The desktop shell holds the child's stdin open for its whole lifetime, so
    EOF is a portable "parent is gone" signal — no pid polling, no orphans.
    """
    stream = sys.stdin
    if stream is None:
        return

    def _run() -> None:
        try:
            while stream.read(1):
                pass
        except Exception:
            pass
        stop = getattr(server, "request_stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                logger.warning("Could not stop the gateway on stdin EOF", exc_info=True)
        # Graceful shutdown usually finishes well inside this window. If a turn
        # refuses to unwind, leave nothing behind.
        time.sleep(3)
        os._exit(0)

    threading.Thread(target=_run, name="stdin-eof-watch", daemon=True).start()


async def _async_main(
    settings: Settings,
    ws_port: int | None = None,
    auth_token: str | None = None,
    exit_on_stdin_eof: bool = False,
    ready_file: str | None = None,
) -> None:
    loop = asyncio.get_running_loop()
    orig_handler = loop.get_exception_handler()

    def _handler(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        # ``winerror`` only exists on Windows; Linux/macOS typeshed has no such
        # attribute, so read it defensively to keep the type check portable.
        if exc is not None and isinstance(exc, OSError) and getattr(exc, "winerror", None) == 6:
            return
        if orig_handler:
            orig_handler(_loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)

    from xiaoqiao.session import _SESSIONS_DIR

    print(f"Gateway starting, sessions → {_SESSIONS_DIR}", file=sys.stderr, flush=True)

    skill_provider = create_skills_provider()
    mcp_tools = create_mcp_tools()

    if ws_port is not None:
        from xiaoqiao.gateway.ws_server import WsGatewayServer

        server = WsGatewayServer(
            tools=create_coding_tools(approval_config=settings.approval_config()),
            settings=settings,
            port=ws_port,
            skill_provider=skill_provider,
            mcp_tools=mcp_tools,
            auth_token=auth_token,
            ready_file=ready_file,
        )
        if exit_on_stdin_eof:
            _watch_stdin_eof(server)
        await server.run_forever()
    else:
        from xiaoqiao.gateway.server import GatewayServer
        from xiaoqiao.gateway.transport import StdioTransport

        server = GatewayServer(
            client=_build_client(settings),
            tools=create_coding_tools(approval_config=settings.approval_config()),
            transport=StdioTransport(),
            settings=settings,
            skill_provider=skill_provider,
            mcp_tools=mcp_tools,
        )
        await server.run()


def _run_config_command(argv: list[str]) -> int | None:
    """Handle ``xiaoqiao config <path|show>``; ``None`` means "not a config command".

    ``path`` prints the effective file locations, ``show`` the parsed values with
    every secret masked — the two things people need when a setting "doesn't work".
    """
    if not argv or argv[0] != "config":
        return None

    from xiaoqiao.paths import config_path, mcp_config_path
    from xiaoqiao.settings import to_wire

    action = argv[1] if len(argv) > 1 else "path"
    if action == "path":
        print(config_path())
        print(mcp_config_path())
        return 0
    if action == "show":
        payload = to_wire(load_settings())
        for provider in payload["providers"].values():
            if provider.get("api_key"):
                provider["api_key"] = "***"
        for service in payload["services"].values():
            if service.get("api_key"):
                service["api_key"] = "***"
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"unknown config action: {action} (expected path or show)", file=sys.stderr)
    return 2


def main() -> None:
    config_code = _run_config_command(sys.argv[1:])
    if config_code is not None:
        sys.exit(config_code)

    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    settings = _merge_settings(args)

    if args.test is not None:
        prompt = " ".join(args.test) or "Hello"
        asyncio.run(_run_test_mode(prompt, settings))
        return

    token = args.auth_token or os.environ.get("XIAOQIAO_TOKEN") or None

    # Desktop shell: the window loads the built frontend from disk, so the
    # engine only exposes the WebSocket gateway. No static server, and never
    # touch other processes' ports (kill-on-conflict is a dev convenience only).
    if args.desktop:
        desktop_port = 0 if args.ws_port is None else args.ws_port
        try:
            asyncio.run(
                _async_main(
                    settings,
                    ws_port=desktop_port,
                    auth_token=token,
                    exit_on_stdin_eof=args.exit_on_stdin_eof,
                    ready_file=args.ready_file,
                )
            )
        except KeyboardInterrupt:
            pass
        return

    if args.web:
        ws_port = args.ws_port or 8765
        _free_port(args.web_port)
        _free_port(ws_port)
        try:
            run_static_server(args.web_root, port=args.web_port)
        except FileNotFoundError as exc:
            logger.error("%s", exc)
            print(f"Error: {exc}", file=sys.stderr)
            print("Hint: build the frontend first with 'cd web && pnpm build'.", file=sys.stderr)
            sys.exit(1)
        except OSError as exc:
            logger.error("Cannot start static server: %s", exc)
            print(f"Error: cannot start static server: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            asyncio.run(_async_main(settings, ws_port=ws_port, auth_token=token, ready_file=args.ready_file))
        except KeyboardInterrupt:
            pass
        return

    if args.ws_port is not None:
        _free_port(args.ws_port)
        try:
            asyncio.run(_async_main(settings, ws_port=args.ws_port, auth_token=token, ready_file=args.ready_file))
        except KeyboardInterrupt:
            pass
        return

    # stdio gateway mode (legacy)
    sys.stdout = _StreamToLogger()  # type: ignore[assignment]
    try:
        asyncio.run(_async_main(settings, ws_port=None))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
