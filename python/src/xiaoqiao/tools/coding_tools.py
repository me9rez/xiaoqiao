"""小巧 tools — file read/write/edit/search, shell commands, system utilities.

Each tool is a ``FunctionTool`` instance that can be passed to the agent loop.
All tools are async and return strings.
"""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import json
import logging
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agent_framework._tools import FunctionTool

from agent_framework._middleware import FunctionInvocationContext

from xiaoqiao.paths import config_dir

ApprovalMode = Literal["always_require", "never_require"]

logger = logging.getLogger(__name__)


@dataclass
class _ToolResult:
    """Structured result for tools that have exit codes / ok status."""

    type: str = "tool_result"
    result: str = ""
    exit_code: int | None = None
    ok: bool = True


_MAX_OUTPUT_CHARS = 100_000
_DATA_DIR = config_dir()

# Default tools that require approval
_DEFAULT_ALWAYS_REQUIRE = {"run_command", "write_file", "edit_file", "http_fetch"}


def _ensure_data_dir() -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def _get_approval_mode(tool_name: str, approval_config: dict[str, Any]) -> ApprovalMode | None:
    """Determine the approval mode for a tool based on configuration.

    Patterns may be exact tool names or prefix globs (``mcp__github__*``), the
    same matching the permission rules in ``config.toml`` use.
    """
    if not approval_config.get("enabled", True):
        return None

    always_require = approval_config.get("always_require", _DEFAULT_ALWAYS_REQUIRE)
    never_require = approval_config.get("never_require", [])

    if any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in never_require):
        return None
    if any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in always_require):
        mode: ApprovalMode = "always_require"
        return mode
    return None


def _get_approval_mode_for_tool(tool_name: str, approval_config: dict[str, Any]) -> ApprovalMode | None:
    """Wrapper to get approval mode for a specific tool."""
    return _get_approval_mode(tool_name, approval_config)


def create_coding_tools(
    approval_config: dict[str, Any] | None = None,
) -> list[FunctionTool]:
    """Return the default set of coding tools.

    Args:
        approval_config: Tool approval configuration from settings.
            If None, uses default approval settings.

    All tools use ``result_parser=SKIP_PARSING`` so that the agent loop's
    function middleware can observe raw return values (including ``_ToolResult``)
    and emit fine-grained ``ToolExecutionEndEvent`` data such as ``exit_code``.
    """
    from agent_framework._tools import SKIP_PARSING, FunctionTool

    if approval_config is None:
        approval_config = {"enabled": True, "always_require": list(_DEFAULT_ALWAYS_REQUIRE)}

    def _approval(name: str) -> ApprovalMode | None:
        return _get_approval_mode(name, approval_config)

    return [
        FunctionTool(
            name="run_command",
            description="Execute a shell command",
            func=_run_command,
            result_parser=SKIP_PARSING,
            approval_mode=_approval("run_command"),
        ),
        FunctionTool(
            name="read_file",
            description="Read the contents of a file",
            func=_read_file,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="write_file",
            description="Write content to a file (creates parent dirs)",
            func=_write_file,
            result_parser=SKIP_PARSING,
            approval_mode=_approval("write_file"),
        ),
        FunctionTool(
            name="edit_file",
            description=(
                "Edit a file using exact text replacements. "
                "Provide edits as [{oldText, newText}, ...]. "
                "Each oldText must match a unique, non-overlapping region."
            ),
            func=_edit_file,
            result_parser=SKIP_PARSING,
            approval_mode=_approval("edit_file"),
        ),
        FunctionTool(
            name="search_files",
            description="Search file contents recursively with a regex pattern",
            func=_search_files,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="list_directory",
            description="List files and directories at a path",
            func=_list_directory,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="find_files",
            description="Find files by glob pattern (*.py, README*). Excludes .git/node_modules/__pycache__.",
            func=_find_files,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="get_system_info",
            description="Get system environment info (platform, username, home directory, common paths).",
            func=_get_system_info,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="http_fetch",
            description="Send HTTP request to a URL. Supports GET/POST/PUT/DELETE/PATCH.",
            func=_http_fetch,
            result_parser=SKIP_PARSING,
            approval_mode=_approval("http_fetch"),
        ),
        FunctionTool(
            name="web_search",
            description="Search the web for information. Returns titles, URLs, and snippets.",
            func=_web_search,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="system_notify",
            description="Send a desktop notification. Use when the user asks to be notified.",
            func=_system_notify,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="clipboard_read",
            description="Read text content from the system clipboard.",
            func=_clipboard_read,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="clipboard_write",
            description="Write text content to the system clipboard.",
            func=_clipboard_write,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="todo_write",
            description="Manage task plan items. Actions: set (batch create), add, update (change status), read.",
            func=_todo_write,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="report_plan",
            description="Report execution plan steps before starting a task.",
            func=_report_plan,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="log_task_completion",
            description="Log a completed task summary with category and success status.",
            func=_log_task_completion,
            result_parser=SKIP_PARSING,
        ),
        FunctionTool(
            name="ask_user_question",
            description=(
                "Present structured questions to the user and wait for answers. "
                "Use when multiple equivalent paths exist and you need user preference, "
                "or when you cannot infer a key decision from context."
            ),
            func=_ask_user_question,
            result_parser=SKIP_PARSING,
        ),
    ]


# ── run_command ──────────────────────────────────────────────────


async def _run_command(command: str, timeout_seconds: float = 30.0) -> _ToolResult:
    """Execute a shell command and return stdout + stderr."""
    logger.info("run_command: %s", command[:200])
    try:
        if sys.platform == "win32":
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                ),
                timeout=timeout_seconds,
            )
        else:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                ),
                timeout=timeout_seconds,
            )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + f"\n… (truncated, {len(output)} total chars)"
        exit_code = proc.returncode or 0
        return _ToolResult(result=output, exit_code=exit_code, ok=exit_code == 0)
    except TimeoutError:
        return _ToolResult(result=f"Error: Command timed out after {timeout_seconds}s", exit_code=-1, ok=False)
    except Exception as exc:
        return _ToolResult(result=f"Error: {exc}", exit_code=-1, ok=False)


# ── read_file ────────────────────────────────────────────────────


async def _read_file(path: str) -> str:
    """Read the contents of a file."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > _MAX_OUTPUT_CHARS:
            content = content[:_MAX_OUTPUT_CHARS] + f"\n… (truncated, {len(content)} total chars)"
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"


# ── write_file ───────────────────────────────────────────────────


async def _write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed."""
    try:
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error writing file: {exc}"


# ── edit_file (exact text replacement) ───────────────────────────


async def _edit_file(path: str, edits: list[dict[str, str]]) -> str:
    """Apply exact text replacements to a file."""
    try:
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: File not found: {path}"
        if not p.is_file():
            return f"Error: Not a file: {path}"

        raw = p.read_text(encoding="utf-8")
        content = raw.replace("\r\n", "\n").replace("\r", "\n")

        spans: list[tuple[int, int, str]] = []
        for i, edit in enumerate(edits):
            old = edit.get("oldText", "")
            new = edit.get("newText", "")
            if not old:
                return f"Error: edits[{i}].oldText is empty"
            old_norm = old.replace("\r\n", "\n").replace("\r", "\n")
            count = content.count(old_norm)
            if count == 0:
                return (
                    f"Error: edits[{i}].oldText not found in {path}. "
                    "oldText must match a unique region of the file content."
                )
            if count > 1:
                return (
                    f"Error: edits[{i}].oldText found {count} times in {path}. Each oldText must appear exactly once."
                )
            start = content.index(old_norm)
            spans.append((start, start + len(old_norm), new))

        spans.sort(key=lambda s: s[0])
        for i in range(1, len(spans)):
            if spans[i][0] < spans[i - 1][1]:
                return f"Error: edits[{i}] overlaps with edits[{i - 1}]. Edit spans must not overlap."

        new_content = content
        for start, end, new_text in reversed(spans):
            new_content = new_content[:start] + new_text + new_content[end:]

        if new_content == content:
            return f"Warning: No changes made to {path} (oldText matched newText)"

        p.write_text(new_content, encoding="utf-8")

        old_lines = content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(old_lines, new_lines, str(path), str(path)))

        return f"Applied {len(edits)} edit(s) to {path}.\n\n{diff}"

    except Exception as exc:
        return f"Error editing file: {exc}"


# ── search_files ─────────────────────────────────────────────────


async def _search_files(pattern: str, path: str = ".") -> str:
    """Search file contents recursively using a regex pattern."""
    try:
        root = Path(path).resolve()
        if not root.is_dir():
            return f"Error: Not a directory: {path}"
        compiled = re.compile(pattern, re.IGNORECASE)
        results: list[str] = []
        max_results = 50
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix in (".pyc", ".exe", ".dll", ".so", ".dylib", ".bin", ".png", ".jpg", ".gif"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                for lineno, line in enumerate(text.splitlines(), 1):
                    if compiled.search(line):
                        rel = p.relative_to(root)
                        results.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break
            except Exception:
                continue
        if not results:
            return f"No matches for pattern: {pattern}"
        return "\n".join(results) + (f"\n… (showing {len(results)} of many)" if len(results) >= max_results else "")
    except re.error as exc:
        return f"Invalid regex pattern: {exc}"
    except Exception as exc:
        return f"Error searching files: {exc}"


# ── list_directory ───────────────────────────────────────────────


async def _list_directory(path: str = ".") -> str:
    """List files and directories at the given path."""
    try:
        p = Path(path).resolve()
        if not p.is_dir():
            return f"Error: Not a directory: {path}"
        entries = [f"{p}/"]
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            entries.append(f"  {entry.name}{'/' if entry.is_dir() else ''}")
        return "\n".join(entries) if entries else "(empty)"
    except Exception as exc:
        return f"Error listing directory: {exc}"


# ── find_files ───────────────────────────────────────────────────


async def _find_files(pattern: str, path: str = ".", max_results: int = 100) -> str:
    """Find files by glob pattern, excluding common non-source directories."""
    try:
        root = Path(path).resolve()
        if not root.is_dir():
            return f"Error: Not a directory: {path}"
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
        results: list[str] = []
        for p in root.rglob(pattern):
            if any(part in skip_dirs for part in p.parts):
                continue
            if p.is_file():
                results.append(str(p.relative_to(root)))
                if len(results) >= max_results:
                    break
        if not results:
            return f"No files found matching pattern: {pattern}"
        header = f"Found {len(results)}" + ("+" if len(results) >= max_results else "") + " files:"
        return header + "\n" + "\n".join(results)
    except Exception as exc:
        return f"Error finding files: {exc}"


# ── get_system_info ──────────────────────────────────────────────


async def _get_system_info() -> str:
    """Get system environment information."""
    try:
        home = Path.home()
        info = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "username": os.getenv("USERNAME") or os.getenv("USER") or "unknown",
            "home_directory": str(home),
            "desktop": str(home / "Desktop"),
            "documents": str(home / "Documents"),
            "downloads": str(home / "Downloads"),
            "cwd": os.getcwd(),
        }
        return json.dumps(info, indent=2, ensure_ascii=False)
    except Exception as exc:
        return f"Error getting system info: {exc}"


# ── http_fetch ───────────────────────────────────────────────────


async def _http_fetch(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> str:
    """Send an HTTP request and return the response."""
    try:
        import httpx
    except ImportError:
        return "Error: httpx is not installed. Run: uv add httpx"

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            kwargs: dict = {"method": method.upper(), "url": url, "headers": headers or {}}
            if body and method.upper() in ("POST", "PUT", "PATCH"):
                kwargs["content"] = body
            resp = await client.request(**kwargs)
            text = resp.text
            if len(text) > _MAX_OUTPUT_CHARS:
                text = text[:_MAX_OUTPUT_CHARS] + f"\n… (truncated, {len(text)} total chars)"
            return f"HTTP {resp.status_code} {resp.reason_phrase}\n\n{text}"
    except Exception as exc:
        return f"Error making HTTP request: {exc}"


# ── web_search ───────────────────────────────────────────────────


async def _web_search(query: str, count: int = 8, market: str = "zh-CN") -> str:
    """Search the web using the provider configured in ``[services.web_search]``."""
    try:
        from xiaoqiao.settings import load as load_settings

        service = load_settings().services.get("web_search")
        provider = (service.provider if service else "") or "bing"
        api_key = service.api_key if service else ""
        base_url = service.base_url if service else ""

        if not api_key:
            return "Error: No search API key configured. Set [services.web_search] api_key in ~/.xiaoqiao/config.toml"

        if provider == "bing":
            return await _bing_search(query, api_key, count, market)
        elif provider == "searxng":
            if not base_url:
                return "Error: No SearXNG URL configured. Set [services.web_search] base_url in config.toml."
            return await _searxng_search(query, base_url, count)
        else:
            return f"Error: Unknown search provider '{provider}'. Supported: bing, searxng"
    except Exception as exc:
        return f"Error searching web: {exc}"


async def _bing_search(query: str, api_key: str, count: int, market: str) -> str:
    """Search using Bing Web Search API."""
    import httpx

    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {"q": query, "count": min(count, 20), "mkt": market}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            return f"Bing search error: {resp.status_code} {resp.text[:500]}"
        data = resp.json()
        results = data.get("webPages", {}).get("value", [])
        if not results:
            return f"No results for: {query}"
        lines = []
        for i, r in enumerate(results[:count], 1):
            lines.append(f"{i}. **{r.get('name', '')}** — {r.get('url', '')}")
            lines.append(f"   {r.get('snippet', '')}")
        return f"Search results ({len(lines) // 2}):\n\n" + "\n".join(lines)


async def _searxng_search(query: str, base_url: str, count: int) -> str:
    """Search using a SearXNG instance."""
    import httpx

    url = f"{base_url.rstrip('/')}/search"
    params = {"q": query, "format": "json", "categories": "general"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return f"SearXNG error: {resp.status_code} {resp.text[:500]}"
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return f"No results for: {query}"
        lines = []
        for i, r in enumerate(results[:count], 1):
            lines.append(f"{i}. **{r.get('title', '')}** — {r.get('url', '')}")
            lines.append(f"   {r.get('content', '')[:200]}")
        return f"Search results ({len(lines) // 2}):\n\n" + "\n".join(lines)


# ── system_notify ────────────────────────────────────────────────


async def _system_notify(title: str, body: str) -> str:
    """Send a desktop notification."""
    try:
        if sys.platform == "win32":
            ps_script = (
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null"
                "[Windows.Data.Xml.Dom.XmlDocument, "
                "Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null"
                f'$t = \'<toast><visual><binding template="ToastText02">'
                f'<text id="1">{title}</text>'
                f'<text id="2">{body}</text></binding></visual></toast>\''
                "$x = New-Object Windows.Data.Xml.Dom.XmlDocument"
                "$x.LoadXml($t)"
                "$n = [Windows.UI.Notifications.ToastNotification]::new($x)"
                "[Windows.UI.Notifications.ToastNotificationManager]"
                "::CreateToastNotifier('小巧').Show($n)"
            )
            proc = await asyncio.create_subprocess_exec(
                "pwsh",
                "-NoProfile",
                "-Command",
                ps_script,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return "Notification sent."
        elif sys.platform == "darwin":
            script = f'display notification "{body}" with title "{title}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript",
                "-e",
                script,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return "Notification sent."
        else:
            proc = await asyncio.create_subprocess_exec(
                "notify-send",
                title,
                body,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return "Notification sent."
    except Exception as exc:
        return f"Error sending notification: {exc}"


# ── clipboard_read ───────────────────────────────────────────────


async def _clipboard_read() -> str:
    """Read text from the system clipboard."""
    try:
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_exec(
                "pwsh",
                "-NoProfile",
                "-Command",
                "Get-Clipboard",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("utf-8", errors="replace").strip()
            return text or "[clipboard is empty]"
        elif sys.platform == "darwin":
            proc = await asyncio.create_subprocess_exec(
                "pbpaste",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("utf-8", errors="replace").strip()
            return text or "[clipboard is empty]"
        else:
            proc = await asyncio.create_subprocess_exec(
                "xclip",
                "-selection",
                "clipboard",
                "-o",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("utf-8", errors="replace").strip()
            return text or "[clipboard is empty]"
    except Exception as exc:
        return f"Error reading clipboard: {exc}"


# ── clipboard_write ──────────────────────────────────────────────


async def _clipboard_write(text: str) -> str:
    """Write text to the system clipboard."""
    try:
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_exec(
                "pwsh",
                "-NoProfile",
                "-Command",
                f"Set-Clipboard -Value @'\n{text}\n'@",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.wait()
            return "Text copied to clipboard."
        elif sys.platform == "darwin":
            proc = await asyncio.create_subprocess_exec(
                "pbcopy",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.communicate(input=text.encode("utf-8"))
            return "Text copied to clipboard."
        else:
            proc = await asyncio.create_subprocess_exec(
                "xclip",
                "-selection",
                "clipboard",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc.communicate(input=text.encode("utf-8"))
            return "Text copied to clipboard."
    except Exception as exc:
        return f"Error writing to clipboard: {exc}"


# ── todo_write ───────────────────────────────────────────────────


async def _todo_write(
    action: str,
    items: list[dict[str, str]] | None = None,
    todo_id: str | None = None,
    status: str | None = None,
    content: str | None = None,
    ctx: FunctionInvocationContext | None = None,
) -> str:
    """Manage task plan items stored per session in ~/.xiaoqiao/sessions/<id>/todos.json."""
    try:
        session_id = "global"
        if ctx and ctx.session:
            session_id = ctx.session._session_id

        session_dir = _ensure_data_dir() / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        todos_path = session_dir / "todos.json"
        todos: list[dict] = json.loads(todos_path.read_text(encoding="utf-8")) if todos_path.exists() else []

        if action == "set":
            if not items:
                return "Error: items list is required for 'set' action"
            todos = []
            for i, item in enumerate(items):
                todos.append(
                    {
                        "id": f"t{i + 1}",
                        "content": item.get("content", ""),
                        "status": item.get("status", "pending"),
                    }
                )
            todos_path.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"Created {len(todos)} todo items.\n" + _format_todos(todos)

        elif action == "add":
            if not content:
                return "Error: content is required for 'add' action"
            new_id = f"t{len(todos) + 1}"
            todos.append({"id": new_id, "content": content, "status": "pending"})
            todos_path.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"Added todo: {content} (ID: {new_id})"

        elif action == "update":
            if not todo_id:
                return "Error: todo_id is required for 'update' action"
            for todo in todos:
                if todo["id"] == todo_id:
                    if status:
                        todo["status"] = status
                    if content:
                        todo["content"] = content
                    todos_path.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")
                    return f"Updated {todo_id}: {todo['content']} → {todo['status']}"
            return f"Error: todo '{todo_id}' not found"

        elif action == "read":
            if not todos:
                return "No todo items. Use 'set' or 'add' to create."
            return _format_todos(todos)

        else:
            return f"Error: unknown action '{action}'. Valid: set, add, update, read"
    except Exception as exc:
        return f"Error managing todos: {exc}"


def _format_todos(todos: list[dict]) -> str:
    status_icons = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]", "cancelled": "[-]"}
    lines = [f"  {status_icons.get(t['status'], '[ ]')} {t['id']}: {t['content']}" for t in todos]
    return "Todo items:\n" + "\n".join(lines)


# ── report_plan ──────────────────────────────────────────────────


async def _report_plan(steps: list[str], ctx: FunctionInvocationContext | None = None) -> str:
    """Report execution plan steps. Records per session in ~/.xiaoqiao/sessions/<id>/plans.json."""
    try:
        session_id = "global"
        if ctx and ctx.session:
            session_id = ctx.session._session_id

        session_dir = _ensure_data_dir() / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        plans_path = session_dir / "plans.json"
        plans: list[dict] = json.loads(plans_path.read_text(encoding="utf-8")) if plans_path.exists() else []

        import time

        plan = {
            "id": f"plan-{int(time.time())}",
            "steps": steps,
            "status": "reported",
        }
        plans.append(plan)
        plans_path.write_text(json.dumps(plans, indent=2, ensure_ascii=False), encoding="utf-8")

        step_list = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps))
        return f"Plan recorded ({len(steps)} steps):\n{step_list}"
    except Exception as exc:
        return f"Error reporting plan: {exc}"


# ── log_task_completion ──────────────────────────────────────────


async def _log_task_completion(
    summary: str,
    category: str,
    success: bool,
    ctx: FunctionInvocationContext | None = None,
) -> str:
    """Log a completed task per session in ~/.xiaoqiao/sessions/<id>/task_log.jsonl."""
    try:
        import time

        session_id = "global"
        if ctx and ctx.session:
            session_id = ctx.session._session_id

        session_dir = _ensure_data_dir() / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        log_path = session_dir / "task_log.jsonl"

        entry = {
            "summary": summary,
            "category": category,
            "success": success,
            "timestamp": int(time.time() * 1000),
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        status = "completed" if success else "failed"
        return f"Task logged [{status}]: {summary}"
    except Exception as exc:
        return f"Error logging task: {exc}"


# ── ask_user_question ────────────────────────────────────────────


async def _ask_user_question(
    questions: list[dict],
) -> str:
    """Present structured questions to the user and wait for answers via stdin.

    Each question should have:
    - header: short label (max 12 chars)
    - question: full question text
    - multiSelect: boolean (true = multiple choice, false = single choice)
    - options: list of {label, description?} (2-4 options)
    """
    import asyncio

    try:
        if not questions or len(questions) < 1 or len(questions) > 4:
            return "Error: questions array must have 1-4 items"

        lines: list[str] = []
        for i, q in enumerate(questions):
            header = q.get("header", "")
            question = q.get("question", "")
            multi_select = q.get("multiSelect", False)
            options = q.get("options", [])

            if not header or not question:
                return f"Error: question {i + 1} missing header or question"
            if len(options) < 2 or len(options) > 4:
                return f"Error: question {i + 1} must have 2-4 options"

            mode = "多选" if multi_select else "单选"
            lines.append(f"\n[{header}] ({mode}) {question}")
            for j, opt in enumerate(options, 1):
                desc = f" - {opt.get('description', '')}" if opt.get("description") else ""
                lines.append(f"  {j}. {opt.get('label', '')}{desc}")

        lines.append("\n请输入选项编号（多个用逗号分隔）：")

        print("\n".join(lines))

        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input, "> ")
        user_input = user_input.strip()

        if not user_input:
            return "用户未作答"

        results: list[str] = []
        for q in questions:
            options = q.get("options", [])
            try:
                indices = [int(x.strip()) - 1 for x in user_input.split(",")]
                selected = []
                for idx in indices:
                    if 0 <= idx < len(options):
                        selected.append(options[idx].get("label", ""))
                if selected:
                    results.append(f"[{q.get('header', '')}] {', '.join(selected)}")
            except ValueError:
                continue

        if results:
            return "用户已作答：\n" + "\n".join(results)
        return f"无效输入：{user_input}"

    except Exception as exc:
        return f"Error asking user: {exc}"
