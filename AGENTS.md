# 小巧（Xiaoqiao）— AGENTS.md

## 仓库结构

两包 monorepo，根目录无直接代码：

- `python/` — agent 核心（agent-framework harness + 工具 + gateway），Python 3.14+
- `web/` — Web 前端（Vue + Vite），Node 22+, pnpm
- 必须 `cd` 进对应目录再执行命令

## Python 层

```bash
cd python
uv sync                    # 安装依赖
ruff check src/            # lint
ruff format --check src/   # 格式化检查
pyright src/               # 类型检查 (pyright)
uv run pytest              # 运行所有单元测试
```

### 单元测试

- **框架**：pytest + pytest-asyncio（`pyproject.toml` 中配置）
- **配置**：`asyncio_mode = "auto"`，测试文件路径 `tests/`
- **位置**：`python/tests/unit/`
- **运行方式**：
  ```bash
  uv run pytest                          # 全部测试
  uv run pytest -v                      # 详细输出
  uv run pytest tests/unit/test_agent_runtime.py  # 指定文件
  uv run pytest -k test_thinking         # 按名称过滤
  uv run pytest --coverage               # 覆盖率报告
  ```
- **测试文件**：
  - `tests/unit/test_agent_runtime.py` — 事件翻译（`TestDispatchUpdate`）、工具中间件与结果规范化（`TestToolEventMiddleware`、`TestExtractToolResult`）
  - `tests/unit/test_settings.py` — 配置加载和客户端构建（`TestBuildClient`）
  - `tests/unit/test_skills.py` — SkillsProvider 创建
  - `tests/unit/test_mcp.py` — MCP 工具创建

### Agent 运行时

agent 运行时基于 agent-framework 的 `create_harness_agent`（函数调用循环、上下文压缩、
历史持久化、工具审批由框架提供）：

- `agent_runtime.py` — `AgentRuntime`：构造 harness agent、翻译流式更新为细粒度事件、审批往返
- `turn_runner.py` — `TurnRunner`：两会话网关共享的编排层
- `tool_events.py` — `ToolEventMiddleware`：补齐框架流不含的工具生命周期事件
- `events.py` — 面向 gateway/前端的事件契约

框架 `AgentSession` 是对话状态的唯一权威（它维护 OpenAI 兼容 API 要求的
`tool_call`/`tool_result` 配对）；JSONL 转录只是它的投影。

**集成测试**（需真实 API key）：
```bash
uv run python -m xiaoqiao.main --test "列出当前目录文件"
```

### 其他

- 构建系统：hatchling，依赖管理：uv（不是 pip）
- Ruff 配置：line-length 120，双引号，target py314
- Python 入口：`xiaoqiao.main:main`
- 发行名与导入包均为 `xiaoqiao`，源码在 `python/src/`，必须让 PYTHONPATH 包含此路径
- API key 优先级：settings.json > `DEEPSEEK_API_KEY` 环境变量 > `OPENAI_API_KEY`
- 添加工具：在 `tools/coding_tools.py` 写 async 函数，在 `create_coding_tools()` 注册 `FunctionTool`，参数名和 docstring 自动转 JSON schema

## Web 层

### 设计规范（硬性）

- UI 改动前先读 `docs/design.md`，它是对 `web/` 有约束力的设计依据。
- 设计值只在 `web/src/styles/tokens.css` 定义；组件内写 `var(--token)`，禁止写死颜色。
- 主题与字号由 `html[data-color-scheme]` / `html[data-font-scale]` 驱动，逻辑在 `web/src/theme.ts`。
- 旧变量（`--bg-page`、`--border`、`--bg-card` 等）仅作迁移兼容，新代码不要使用。
- 暗色只覆盖语义 token，不要在组件里写 `dark:` 分支复制一套颜色。

```bash
cd web
pnpm install               # 安装依赖
pnpm dev                   # 开发服务器（vite）
pnpm type-check            # vue-tsc --build 类型检查
pnpm test:unit             # 运行所有单元测试
pnpm build                 # vite 构建到 dist/
pnpm preview               # 预览构建产物
```

### 单元测试

- **框架**：vitest（`vitest.config.ts` 中配置）
- **环境**：jsdom
- **位置**：`web/tests/`，命名为 `*.spec.ts`、`*.test.ts`
- **配置**：`vitest.config.ts` 继承 `vite.config.ts`
- **运行方式**：
  ```bash
  pnpm test:unit                            # 全部测试
  pnpm test:unit -- --reporter verbose      # 详细输出
  pnpm test:unit -- tests/stores/chat.test.ts  # 指定文件
  pnpm test:unit -t "convertBackendMessages"  # 按名称过滤
  pnpm test:unit -- --coverage              # 覆盖率报告
  ```
- **测试文件**：
  - `tests/services/gateway.spec.ts` — WebSocket 网关服务
  - `tests/stores/sessions.spec.ts` — 会话 store
  - `tests/stores/chat.test.ts` — 消息转换（`convertBackendMessages`）
  - `tests/stores/chat.wire.test.ts` — 网关 wire 协议转换
  - `tests/components/chat/MessageItem.spec.ts` — 消息组件渲染

### 其他

- 前端入口：`src/main.ts`（Vue 3 + Pinia + Vue Router）
- Web 端通过 WebSocket（`ws://127.0.0.1:8765`，见 `web/src/services/gateway.ts`）连接网关，不直接启动 Python 进程
- 网关协议：websocket（详见 `docs/protocol.md`）

## 配置

所有配置在 `~/.xiaoqiao/settings.json`，支持 model/base_url/api_key/thinking_level/token budgets/max_turns。

用户 skill 在 `~/.xiaoqiao/skills/`，项目 skill 在根 `skills/`。

> 旧目录 `~/.coding-agent/` 仍被兼容读取：新目录不存在、旧目录存在时沿用旧目录（见 `python/src/xiaoqiao/paths.py`）。

## 打包与发布

web 前端构建产物会随 Python wheel 一起分发，用户安装后即可通过 `xiaoqiao --web` 直接运行（`coding-agent` 保留为兼容别名）。

```powershell
# 一键构建 whl（含 web/dist）
.\scripts\build-package.ps1

# 本地测试安装
uv tool install --reinstall python/dist/xiaoqiao-*.whl
xiaoqiao --web

# 构建并发布到 PyPI（需配置 UV_PUBLISH_TOKEN 或 PyPI 凭证）
.\scripts\build-package.ps1 -Publish
```

- 发行名与入口脚本在 `python/pyproject.toml` 中定义（`xiaoqiao` + 兼容别名 `coding-agent`）。
- 运行时会优先使用 wheel 内嵌的 `xiaoqiao/web_dist` 资源，开发环境回退到 `web/dist`。

## 无 CI / 无 pre-commit

仓库没有 CI 配置或 pre-commit hook。修改后手动运行：
1. `ruff check src/`（Python lint）
2. `cd web && pnpm test:unit`（Web 测试）
3. `uv run pytest`（Python 测试）
