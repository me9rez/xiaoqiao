# Gateway JSON-RPC 协议

小巧网关通过两种传输层暴露同一套 JSON-RPC 消息协议：

- **WebSocket**（`--ws-port`，Web 界面使用）：每条消息为一个 JSON frame。
- **stdio**（遗留 TUI）：通过 `stdin`/`stdout` 传输 newline-delimited JSON。

无论哪种传输，每个消息都是一个 JSON 对象。

Web 界面示例：
```
WS → {"method":"prompt","params":{"text":"..."}}
WS ← {"type":"text_delta","delta":"..."}
WS ← {"type":"done"}
```

遗留 stdio 示例：
```
TUI ──stdin──→ {"method":"prompt","params":{"text":"..."}}
TUI ←─stdout── {"type":"text_delta","delta":"..."}
TUI ←─stdout── {"type":"done"}
```

## 启动

网关启动后立即发送 `ready` 事件。WebSocket 网关还会附带当前工作区信息：

```
← {"type":"ready"}
```

或

```json
{"type":"ready","workspace":{"name":"xiaoqiao","path":"/home/user/xiaoqiao"}}
```

表示网关已就绪，可以接受请求。

## 事件（gateway → TUI）

### text_delta
```json
{"type":"text_delta","delta":"你好！"}
```
模型流式输出的可见文本 token。

### thinking_delta
```json
{"type":"thinking_delta","delta":"用户想要..."}
```
推理/思考 token（来自支持 extended thinking 的 provider，如 Anthropic）。

### tool_call_start
```json
{"type":"tool_call_start","callId":"call_xxx","name":"bash","arguments":"{\"command\":\"ls\"}"}
```
LLM 发起了一个工具调用。所有参数在 `arguments` JSON 字符串中可用。

### tool_execution_start
```json
{"type":"tool_execution_start","callId":"call_xxx","name":"bash"}
```
工具开始执行。

### tool_execution_delta
```json
{"type":"tool_execution_delta","callId":"call_xxx","line":"file1.py\n"}
```
工具运行中的增量输出（例如 shell 命令的 stdout 行）。

### tool_execution_end
```json
{"type":"tool_execution_end","callId":"call_xxx","name":"bash","ok":true,"exitCode":0}
```
工具执行完成。`ok` 表示成功与否；`exitCode` 是进程退出码。

### turn_end
```json
{"type":"turn_end","reason":"complete"}
```
```json
{"type":"turn_end","reason":"tool_calls"}
```
一个 agent 轮次完成。`reason` 含义：
- `complete`: 无需更多工具调用，最终响应就绪
- `tool_calls`: 将有工具调用紧随其后

### done
```json
{"type":"done"}
```
整个 agent 运行结束。TUI 应回到空闲状态。

### error
```json
{"type":"error","message":"Agent run cancelled","recoverable":true}
```
```json
{"type":"error","message":"Connection failed","recoverable":false}
```
发生错误。`recoverable: true` 表示 agent 可继续；`false` 表示运行应停止。

### rpc_response
```json
{"type":"rpc_response","id":"req-1","result":[{"id":"abc","title":"hello","messageCount":2,"createdAt":"...","updatedAt":"..."}]}
```
```json
{"type":"rpc_response","id":"req-2","error":{"message":"Session not found"}}
```
对带有 `id` 的 RPC 请求的响应。客户端通过 `id` 关联；成功时结果在 `result` 中，失败时返回 `error` 对象。

## 请求（TUI → gateway）

### prompt
```json
{"method":"prompt","params":{"text":"列出 Python 文件"}}
```
```json
{"method":"prompt","params":{"text":"继续","sessionId":"abc123"}}
```
向 agent 发送用户消息。如果提供 `sessionId`，网关恢复该会话。

### cancel
```json
{"method":"cancel","params":{}}
```
取消当前 agent 运行。网关会发出 `error` 事件，`recoverable: true`。

## RPC 请求

RPC 请求需包含唯一 `id`，网关会返回对应的 `rpc_response` 事件。

### listSessions
```json
{"id":"req-1","method":"listSessions","params":{}}
```
返回会话元数据列表，最新的在前。

### createSession
```json
{"id":"req-2","method":"createSession","params":{"title":"新对话"}}
```
创建并持久化一个新会话，返回完整会话对象。

### loadSession
```json
{"id":"req-3","method":"loadSession","params":{"sessionId":"abc123"}}
```
加载指定会话及其消息。

### updateSession
```json
{"id":"req-4","method":"updateSession","params":{"sessionId":"abc123","title":"重命名"}}
```
更新会话标题。

### deleteSession
```json
{"id":"req-5","method":"deleteSession","params":{"sessionId":"abc123"}}
```
删除会话，成功返回 `{"ok": true}`。

### getSettings / updateSettings
```json
{"id":"req-6","method":"getSettings","params":{}}
{"id":"req-7","method":"updateSettings","params":{"selectedModel":"deepseek/deepseek-v4-flash"}}
```
读取或更新当前 provider/model 设置。

> RPC 请求由 **WebSocket 网关**（`gateway/ws_server.py`）实现。遗留 stdio 网关仅支持 `prompt` 和 `cancel`。

## 对话示例

```
TUI → {"method":"prompt","params":{"text":"echo hello"}}

TUI ← {"type":"text_delta","delta":"让我"}
TUI ← {"type":"text_delta","delta":"执行"}
TUI ← {"type":"text_delta","delta":"这个命令..."}
TUI ← {"type":"turn_end","reason":"tool_calls"}
TUI ← {"type":"tool_call_start","callId":"call_1","name":"bash","arguments":"{\"command\":\"echo hello\"}"}
TUI ← {"type":"tool_execution_start","callId":"call_1","name":"bash"}
TUI ← {"type":"tool_execution_end","callId":"call_1","name":"bash","ok":true,"exitCode":0}
TUI ← {"type":"text_delta","delta":"完成!"}
TUI ← {"type":"turn_end","reason":"complete"}
TUI ← {"type":"done"}
```
