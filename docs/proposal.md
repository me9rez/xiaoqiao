# 小巧（Xiaoqiao）— 技术方案

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│ Python: agent-framework（building blocks）                    │
│  ├─ BaseChatClient           LLM 流式调用                     │
│  ├─ FunctionTool             工具定义与执行                    │
│  ├─ Message / Content        统一消息模型                      │
│  └─ ContextWindowCompactionStrategy  上下文压缩               │
├──────────────────────────────────────────────────────────────┤
│ Python: xiaoqiao（自定义 loop + gateway）                 │
│  ├─ loop.py                  自定义 agent loop                │
│  │   └─ BaseChatClient.get_response(stream=True)              │
│  │   └─ 每轮产出自定义细粒度事件流                             │
│  ├─ events.py                事件类型定义                      │
│  ├─ gateway/ws_server.py     WebSocket JSON-RPC gateway       │
│  ├─ gateway/server.py        遗留 stdio JSON-RPC gateway      │
│  ├─ gateway/transport.py     StdioTransport                   │
│  ├─ session.py               JSONL 会话持久化                 │
│  ├─ skills.py                SKILL.md 扫描与加载               │
│  ├─ system_prompt.py         System prompt + 项目上下文        │
│  └─ tools/coding_tools.py    bash / 文件 / 搜索等工具          │
├──────────────────────────────────────────────────────────────┤
│ TypeScript: Web frontend                                     │
│  ├─ services/gateway.ts      WebSocket 客户端 + RPC           │
│  ├─ stores/                  Pinia 状态（chat / sessions / workspace）│
│  ├─ views/ChatView.vue       聊天主界面                        │
│  ├─ components/chat/         MessageItem / Sidebar / ContextPanel 等│
│  └─ main.ts                  应用入口                          │
└──────────────────────────────────────────────────────────────┘
```

### 为什么不用 `create_harness_agent`

`create_harness_agent` 打包了 `FunctionInvocationLayer + AgentLoopMiddleware`，但它的 streaming 事件粒度太粗——tool call 执行和 thinking delta 都被吞在内部。我们需要的不是 `AgentResponseUpdate(contents=[TextContent])`，而是：

| 事件 | 说明 | Web UI 用途 |
|------|------|-------------|
| `thinking_delta` | reasoning token 逐 chunk | ContextPanel / 消息 thinking 块 |
| `text_delta` | 可见文本逐 chunk | 消息正文流式渲染 |
| `tool_call_start` | LLM 发起 tool call | 显示工具调用卡片 |
| `tool_execution_start` | tool 开始执行 | 卡片显示运行中状态 |
| `tool_execution_delta` | tool 输出（stdout 行） | 卡片内实时日志 |
| `tool_execution_end` | tool 完成（exit code） | 卡片更新成功/失败 |
| `turn_end` | 一轮 LLM+tool 完成 | 切换下一轮状态 |

方案：用 `BaseChatClient.get_response(stream=True)` 自己做 loop，在每个点发射上述事件。

---

## 2. 事件粒度问题 vs 实现方案

### 问题重现

`FunctionInvocationLayer.get_response(stream=True)` 内部循环：

```python
async def _stream():
    for attempt in range(max_iterations):
        inner_stream = super_get_response(messages, stream=True, ...)  # LLM 调用
        async for update in inner_stream:
            yield update                                           # 只 yield text delta
        
        response = await inner_stream.get_final_response()
        result = await _process_function_requests(response, ...)    # 静默执行 tool
        if result.get("action") == "continue":
            continue
```

外部 stream 看到的是：

```
ChatResponseUpdate(text="让我查一下...")
ChatResponseUpdate(text="用 Python 的话...")
→ [静默: tool call → execute bash → 拿结果 → 再调 LLM]
ChatResponseUpdate(text="结果出来了...")
```

中间缺失：thinking delta、tool call 开始/执行/结束。

### 实现方案：自定义 loop + BaseChatClient

不用 `create_harness_agent`，直接用 `BaseChatClient.get_response()` 自己做 loop：

```python
# loop.py
async def run_xiaoqiao(client, messages, tools, on_event):
    tools = normalize_tools(tools)
    tool_map = {t.name: t for t in tools}
    
    while True:
        stream = client.get_response(messages, stream=True, options=dict(tools=tools))
        pending_calls = []
        
        async for update in stream:
            # thinking delta
            raw = update.raw_representation
            if raw and getattr(raw, "type", None) == "content_block_delta":
                if raw.delta.type == "thinking":
                    on_event(ThinkingDeltaEvent(delta=raw.delta.thinking))
            
            # text delta / tool call
            for c in update.contents or []:
                if c.type == "text":
                    on_event(TextDeltaEvent(delta=c.text))
                elif c.type == "function_call":
                    on_event(ToolCallStartEvent(name=c.name, call_id=c.call_id))
                    pending_calls.append(c)
        
        response = await stream.get_final_response()
        
        if not pending_calls:
            on_event(TurnEndEvent(reason="complete"))
            break
        
        for tc in pending_calls:
            on_event(ToolExecutionStartEvent(call_id=tc.call_id, name=tc.name))
            result = await execute_tool(tc, tool_map)
            if result.streaming:
                async for line in result.streaming:
                    on_event(ToolExecutionDeltaEvent(call_id=tc.call_id, line=line))
            on_event(ToolExecutionEndEvent(call_id=tc.call_id, ok=result.ok))
            messages.append(result.to_message())
        
        on_event(TurnEndEvent(reason="tool_calls"))
```

**优点**：完全控制事件粒度，所有事件在正确时机发射，不依赖 provider 特定格式。  
**代价**：约 400 行额外代码；需自行接入 compaction 和 session（agent-framework 组件可复用）。

---

## 3. Gateway 协议

### 通信方式

网关同时支持两种传输：

- **WebSocket**（`gateway/ws_server.py`，默认 `:8765`）：Web UI 使用，每条消息为一个 JSON frame。
- **stdio**（`gateway/server.py` + `transport.py`）：遗留 TUI 使用，newline-delimited JSON。

两种传输的消息格式完全相同。

### 事件流（gateway → client）

```json
{"type":"thinking_delta","delta":"..."}
{"type":"text_delta","delta":"..."}
{"type":"tool_call_start","call_id":"call_1","name":"bash"}
{"type":"tool_execution_start","call_id":"call_1","name":"bash"}
{"type":"tool_execution_delta","call_id":"call_1","line":"$ ls\n"}
{"type":"tool_execution_end","call_id":"call_1","ok":true,"exitCode":0}
{"type":"turn_end","reason":"tool_calls"}
{"type":"text_delta","delta":"结果是..."}
{"type":"done"}
```

### 请求流（client → gateway）

```json
{"method":"prompt","params":{"text":"写一个 Python 脚本"}}
{"method":"cancel","params":{}}
```

WebSocket 网关还支持会话管理 RPC：

```json
{"id":"req-1","method":"listSessions","params":{}}
{"id":"req-2","method":"createSession","params":{"title":"新对话"}}
{"id":"req-3","method":"loadSession","params":{"sessionId":"abc123"}}
{"id":"req-4","method":"updateSession","params":{"sessionId":"abc123","title":"重命名"}}
{"id":"req-5","method":"deleteSession","params":{"sessionId":"abc123"}}
{"id":"req-6","method":"getSettings","params":{}}
```

详见 `docs/protocol.md` / `docs/protocol.zh.md`。

---

## 4. 目录结构

```
xiaoqiao/
├── README.md                    # 项目说明
├── README.zh.md                 # 中文项目说明
├── docs/
│   ├── proposal.md              # 本文
│   ├── protocol.md              # Gateway 协议规范
│   ├── protocol.zh.md           # 协议规范（中文）
│   └── development.md           # 开发指南
│
├── python/
│   ├── pyproject.toml           # 包配置与依赖
│   ├── scripts/
│   │   └── build-package.ps1    # 一键打包发布脚本
│   └── src/
│       └── xiaoqiao/
│           ├── __init__.py
│           ├── __main__.py
│           ├── main.py          # 入口: gateway 模式 / --test CLI
│           ├── loop.py          # 自定义 agent loop
│           ├── events.py        # 细粒度事件类型
│           ├── gateway/
│           │   ├── __init__.py
│           │   ├── ws_server.py # WebSocket JSON-RPC gateway
│           │   ├── server.py    # 遗留 stdio JSON-RPC gateway
│           │   └── transport.py # StdioTransport
│           ├── session.py       # JSONL 会话持久化
│           ├── skills.py        # SKILL.md 扫描 + 渐进式加载
│           ├── system_prompt.py # System prompt + 项目上下文
│           ├── thinking.py      # thinking level 转换
│           ├── compaction.py    # 上下文窗口压缩
│           └── tools/
│               ├── __init__.py
│               └── coding_tools.py  # shell、文件等工具
│
└── web/
    ├── package.json              # 前端依赖
    ├── tsconfig.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── main.ts               # Web app 入口
        ├── router/               # Vue Router
        ├── services/
        │   └── gateway.ts        # WebSocket 客户端
        ├── stores/               # Pinia 状态管理
        ├── types/                # 类型定义
        ├── views/
        │   └── ChatView.vue      # 聊天主界面
        └── components/chat/      # 聊天相关组件
```

---

## 5. 各层关键接口

### Python: `events.py`

```python
@dataclass
class ThinkingDeltaEvent:    delta: str

@dataclass
class TextDeltaEvent:        delta: str

@dataclass
class ToolCallStartEvent:    call_id: str; name: str; arguments: str

@dataclass
class ToolExecutionStartEvent:    call_id: str; name: str

@dataclass
class ToolExecutionDeltaEvent:    call_id: str; line: str

@dataclass
class ToolExecutionEndEvent:      call_id: str; name: str; ok: bool; exit_code: int | None

@dataclass
class TurnEndEvent:         reason: str  # "complete" | "tool_calls"

@dataclass
class DoneEvent:            pass

@dataclass
class ErrorEvent:           message: str; recoverable: bool
```

### Python: `loop.py` 核心签名

```python
async def run_xiaoqiao(
    client: BaseChatClient,
    messages: list[Message],
    tools: list[FunctionTool],
    on_event: Callable[[AgentEvent], None],
    *,
    system_prompt: str | None = None,
    thinking_level: str | None = None,
    compaction_max_tokens: int | None = None,
) -> None
```

### Python: `gateway/ws_server.py`

```python
class WsGatewayServer:
    def __init__(self, client, tools, settings, *, host="127.0.0.1", port=8765): ...
    async def run_forever(self) -> None
```

### TypeScript: `types/gateway.ts`

```typescript
export type AgentEvent =
  | { type: 'thinking_delta'; delta: string }
  | { type: 'text_delta'; delta: string }
  | { type: 'tool_call_start'; callId: string; name: string; arguments: string }
  | { type: 'tool_execution_start'; callId: string; name: string }
  | { type: 'tool_execution_delta'; callId: string; line: string }
  | { type: 'tool_execution_end'; callId: string; name: string; ok: boolean; exitCode: number }
  | { type: 'turn_end'; reason: 'complete' | 'tool_calls' }
  | { type: 'done' }
  | { type: 'error'; message: string; recoverable: boolean }
  | { type: 'ready'; workspace?: { name: string; path: string } }
```

### TypeScript: `services/gateway.ts`

```typescript
class GatewayService {
  connect(): void
  sendPrompt(text: string, sessionId?: string): void
  cancel(): void
  call<T>(method: string, params?: Record<string, unknown>): Promise<T>
  on(event: string, cb: (event: GatewayEvent) => void): () => void
}
```

---

## 6. 已实现阶段

### Phase 1：Python loop + CLI 验证

- `events.py` + `loop.py`：自定义 loop，emit 事件。
- 用 `OpenAIChatClient` / `RawOpenAIChatCompletionClient` 跑通 agent 对话，能看到逐 token thinking 和 tool call 生命周期。
- `--test` CLI 模式支持 fake client，无需 API key。

### Phase 2：WebSocket Gateway + Web UI 原型

- `gateway/ws_server.py`：WebSocket JSON-RPC 派发。
- `services/gateway.ts`：WebSocket 客户端。
- `views/ChatView.vue` + `components/chat/`：消息列表、侧边栏会话、上下文面板、输入框。

### Phase 3：工具 + 配置 + 产品化

- `coding_tools.py`：shell、文件读写/编辑、搜索、目录列表。
- Provider/model 配置、session 持久化、上下文压缩、thinking level。
- 打包脚本 `scripts/build-package.ps1`：构建 web、生成 wheel、发布 PyPI。

---

## 7. 核心依赖

| 层 | 依赖 | 用途 |
|----|------|------|
| Python | `agent-framework-core` | BaseChatClient, Message, Content |
| Python | `agent-framework-openai` / `agent-framework-anthropic` | Provider client |
| Python | `websockets` | WebSocket gateway |
| Python | `hatchling` | Wheel 构建 |
| Web | `vue` | 响应式 UI |
| Web | `pinia` | 状态管理 |
| Web | `vue-router` | 路由 |
| Web | `vue-virtual-scroller` | 长消息列表虚拟滚动 |
| Web | `@unocss/preset-uno` + `@unocss/preset-icons` | 原子样式与图标 |
| Web | `marked` + `highlight.js` | Markdown 渲染与高亮 |
