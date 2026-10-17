# 开发指南

## 仓库结构

```
xiaoqiao/
├── python/          # Agent 核心：自定义 loop、工具、WebSocket 网关
├── web/             # 浏览器界面：Vite + Vue 3 + UnoCSS + Pinia
├── tui/             # 遗留终端界面（供参考）
├── docs/            # 文档
└── scripts/         # 构建/发布脚本
```

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ Python 层                                                    │
│  ┌──────────────┐   ┌─────────────────────────────────────┐ │
│  │ Agent loop   │──▶│ 工具（bash、read、write、edit、     │ │
│  │ loop.py      │   │      search、list_dir、load_skill） │ │
│  └──────┬───────┘   └─────────────────────────────────────┘ │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────┐                     │
│  │ WebSocket 网关                       │                     │
│  │ gateway/ws_server.py :8765          │                     │
│  └──────────────────┬──────────────────┘                     │
└─────────────────────┼───────────────────────────────────────┘
                      │ WebSocket
┌─────────────────────┼───────────────────────────────────────┐
│ Web 层              ▼                                         │
│  ┌─────────────────────────────────────┐                     │
│  │ GatewayService (services/gateway.ts)│                     │
│  └──────────────────┬──────────────────┘                     │
│                     ▼                                         │
│  ┌─────────────────────────────────────┐                     │
│  │ Vue 3 + Pinia + UnoCSS              │                     │
│  │ views/ChatView.vue                  │                     │
│  └─────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

关键设计：

- **自定义 agent loop**（`loop.py`）：逐 chunk 发射 `thinking_delta`、`text_delta`、工具生命周期和轮次边界事件。
- **WebSocket 网关**（`gateway/ws_server.py`）：将 Python 后端与 Web 前端解耦；同样的协议也支持 stdio，供遗留 TUI 使用。
- **会话持久化**（`session.py`）：所有对话以 JSONL 形式保存在 `~/.xiaoqiao/sessions/`（旧目录 `~/.xiaoqiao/` 仍兼容读取）。
- **前端资源打包**：wheel 将 `web/dist` 放入 `xiaoqiao/web_dist`，最终用户只需安装 Python 包。

## Python 层

### 环境准备

```bash
cd python
uv sync
```

### 代码检查

```bash
cd python
uv run ruff check src/
uv run ruff format --check src/
uv run pyright src/
```

### 运行

```bash
# Web 模式：静态资源服务 + WebSocket 网关（使用已构建的 web/dist）
uv run python -m xiaoqiao.main --web

# 仅启动 WebSocket 网关，供 web 开发使用
uv run python -m xiaoqiao.main --ws-port 8765

# CLI 测试模式，使用 fake client（无需 API key）
uv run python -m xiaoqiao.main --test "列出 Python 文件"

# stdio gateway 模式（遗留 TUI）
uv run python -m xiaoqiao.main
```

### 添加新工具

1. 在 `python/src/xiaoqiao/tools/coding_tools.py` 中新增 `async def`。
2. 在 `create_coding_tools()` 中注册为 `FunctionTool`。
3. 参数名和 docstring 会自动转换为 JSON schema。

```python
async def _my_tool(param1: str, param2: int = 42) -> str:
    """工具功能描述。"""
    return f"结果: {param1}, {param2}"

# 在 create_coding_tools() 中：
FunctionTool(name="my_tool", description="工具功能描述。", func=_my_tool),
```

## Web 层

### 环境准备

```bash
cd web
pnpm install
```

### 开发流程

```bash
# 终端 1：启动 WebSocket 网关
cd python
uv run python -m xiaoqiao.main --ws-port 8765

# 终端 2：启动 Vite 开发服务器
cd web
pnpm dev
```

开发服务器默认连接 `ws://127.0.0.1:8765` 的网关。

### 检查

```bash
cd web
pnpm type-check
pnpm test:unit --run
pnpm build
```

## 打包与发布

PowerShell 助手脚本会自动构建前端并生成 wheel：

```powershell
# 在仓库根目录执行
.\scripts\build-package.ps1

# 本地测试安装
uv tool install --reinstall python/dist/xiaoqiao-*.whl

# 发布到 PyPI（需配置 UV_PUBLISH_TOKEN 或 PyPI 凭证）
.\scripts\build-package.ps1 -Publish
```

包元数据见 `python/pyproject.toml`，运行时资源定位逻辑见 `python/src/xiaoqiao/main.py:_default_web_root()`。

## 测试

### 单元/集成测试

```bash
cd web
pnpm test:unit --run
```

Python 测试目前以临时方式运行：

```bash
cd python
# fake client 流程验证（无需 API key）
uv run python -m xiaoqiao.main --test "hello"

# 真实 LLM 验证（需 API key）
uv run python -m xiaoqiao.main --test "执行 echo hello"
```

## 常见问题

### "No module named 'xiaoqiao'"

从 `python/` 目录运行，或将 `python/src` 加入 `PYTHONPATH`。

### Web 界面空白

先构建前端（`cd web && pnpm build`），或直接使用打包脚本（会自动构建）。

### WebSocket 连接失败

确认网关已运行在 Web 客户端期望的端口上（默认 `8765`）。
