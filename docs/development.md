# Development Guide

## Repository layout

```
xiaoqiao/
├── python/          # Agent core: custom loop, tools, WebSocket gateway
├── web/             # Browser UI: Vite + Vue 3 + UnoCSS + Pinia
├── tui/             # Legacy terminal UI (kept for reference)
├── docs/            # Documentation
└── scripts/         # Build/publish helpers
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Python layer                                                │
│  ┌──────────────┐   ┌─────────────────────────────────────┐ │
│  │ Agent loop   │──▶│ Tools (bash, read, write, edit,     │ │
│  │ loop.py      │   │        search, list_dir, load_skill)│ │
│  └──────┬───────┘   └─────────────────────────────────────┘ │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                    │
│  │ WebSocket gateway                   │                    │
│  │ gateway/ws_server.py :8765          │                    │
│  └──────────────────┬──────────────────┘                    │
└─────────────────────┼───────────────────────────────────────┘
                      │ WebSocket
┌─────────────────────┼───────────────────────────────────────┐
│ Web layer           ▼                                         │
│  ┌─────────────────────────────────────┐                    │
│  │ GatewayService (services/gateway.ts)│                    │
│  └──────────────────┬──────────────────┘                    │
│                     ▼                                         │
│  ┌─────────────────────────────────────┐                    │
│  │ Vue 3 + Pinia + UnoCSS              │                    │
│  │ views/ChatView.vue                  │                    │
│  └─────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

Key design choices:

- **Custom agent loop** (`loop.py`) instead of a prefab harness, so we can emit fine-grained events: `thinking_delta`, `text_delta`, tool lifecycle, and turn boundaries.
- **WebSocket gateway** (`gateway/ws_server.py`) decouples the Python backend from the web frontend. The same event protocol is also available over stdio for the legacy TUI.
- **Session persistence** (`session.py`) stores every conversation as JSONL in `~/.xiaoqiao/sessions/` (legacy `~/.xiaoqiao/` still read).
- **Bundled frontend** — the wheel ships `web/dist` under `xiaoqiao/web_dist` so end users only need to install the Python package.

## Python layer

### Setup

```bash
cd python
uv sync
```

### Lint / type-check

```bash
cd python
uv run ruff check src/
uv run ruff format --check src/
uv run pyright src/
```

### Run

```bash
# Web mode: static server + WebSocket gateway (uses built web/dist)
uv run python -m xiaoqiao.main --web

# WebSocket-only gateway for web dev
uv run python -m xiaoqiao.main --ws-port 8765

# CLI test mode with the fake client (no API key required)
uv run python -m xiaoqiao.main --test "List Python files"

# stdio gateway mode (legacy TUI)
uv run python -m xiaoqiao.main
```

### Adding a tool

1. Add an `async def` in `python/src/xiaoqiao/tools/coding_tools.py`.
2. Register it in `create_coding_tools()` as a `FunctionTool`.
3. Parameter names and the docstring become the JSON schema automatically.

```python
async def _my_tool(param1: str, param2: int = 42) -> str:
    """What this tool does."""
    return f"Result: {param1}, {param2}"

# In create_coding_tools():
FunctionTool(name="my_tool", description="What this tool does.", func=_my_tool),
```

## Web layer

### Setup

```bash
cd web
pnpm install
```

### Development workflow

```bash
# Terminal 1: start the WebSocket gateway
cd python
uv run python -m xiaoqiao.main --ws-port 8765

# Terminal 2: start the Vite dev server
cd web
pnpm dev
```

The dev server proxies/expects the gateway at `ws://127.0.0.1:8765`.

### Checks

```bash
cd web
pnpm type-check
pnpm test:unit --run
pnpm build
```

## Packaging and publishing

The PowerShell helper bundles the frontend and builds a wheel:

```powershell
# From the repository root
.\scripts\build-package.ps1

# Local test install
uv tool install --reinstall python/dist/xiaoqiao-*.whl

# Publish to PyPI (requires UV_PUBLISH_TOKEN or PyPI credentials)
.\scripts\build-package.ps1 -Publish
```

See `python/pyproject.toml` for package metadata and `python/src/xiaoqiao/main.py:_default_web_root()` for how the bundled `web_dist` is located at runtime.

## Testing

### Unit / integration tests

```bash
cd web
pnpm test:unit --run
```

Python tests are run ad-hoc:

```bash
cd python
# Fake client pipeline test
uv run python -m xiaoqiao.main --test "hello"

# Real LLM test (requires API key)
uv run python -m xiaoqiao.main --test "Run echo hello"
```

## Common issues

### "No module named 'xiaoqiao'"

Run from the `python/` directory, or ensure `python/src` is on `PYTHONPATH`.

### Web UI shows a blank page

Build the frontend first (`cd web && pnpm build`) or use the packaging script, which does it automatically.

### WebSocket connection fails

Make sure the gateway is running on the port the web client expects (`8765` by default).
