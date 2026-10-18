# Gateway JSON-RPC Protocol

The 小巧 gateway exposes the same JSON-RPC message protocol over two transports:

- **WebSocket** (`--ws-port`, used by the web UI): each message is a single JSON frame.
- **stdio** (legacy TUI): newline-delimited JSON over `stdin`/`stdout`.

In both cases every message is one JSON object.

Web UI example:
```
WS → {"method":"prompt","params":{"text":"..."}}
WS ← {"type":"text_delta","delta":"..."}
WS ← {"type":"done"}
```

Legacy stdio example:
```
TUI ──stdin──→ {"method":"prompt","params":{"text":"..."}}
TUI ←─stdout── {"type":"text_delta","delta":"..."}
TUI ←─stdout── {"type":"done"}
```

## Startup

On startup, the gateway emits a `ready` event. The WebSocket gateway also reports the current working directory:

```
← {"type":"ready"}
```

or

```json
{"type":"ready","workspace":{"name":"xiaoqiao","path":"/home/user/xiaoqiao"}}
```

This signals the client that the gateway is initialized and ready to accept requests.

## Events (gateway → TUI)

### text_delta
```json
{"type":"text_delta","delta":"Hello, world!"}
```
A visible text token emitted during model streaming.

### thinking_delta
```json
{"type":"thinking_delta","delta":"The user wants to..."}
```
A reasoning/thinking token (typically from Anthropic or similar providers that support extended thinking).

### tool_call_start
```json
{"type":"tool_call_start","callId":"call_xxx","name":"bash","arguments":"{\"command\":\"ls\"}"}
```
The LLM has initiated a tool call. All arguments are available in the `arguments` JSON string.

### tool_execution_start
```json
{"type":"tool_execution_start","callId":"call_xxx","name":"bash"}
```
A tool call begins execution.

### tool_execution_delta
```json
{"type":"tool_execution_delta","callId":"call_xxx","line":"file1.py\n"}
```
Incremental output from a running tool (e.g., stdout lines from a shell command).

### tool_execution_end
```json
{"type":"tool_execution_end","callId":"call_xxx","name":"bash","ok":true,"exitCode":0}
```
A tool call has finished execution. `ok` indicates success; `exitCode` is the process exit code.

### turn_end
```json
{"type":"turn_end","reason":"complete"}
```
```json
{"type":"turn_end","reason":"tool_calls"}
```
One agent turn completed. `reason` indicates:
- `complete`: no more tool calls needed, final response ready
- `tool_calls`: tool call(s) will follow

### done
```json
{"type":"done"}
```
The entire agent run is finished. The TUI should return to idle state.

### error
```json
{"type":"error","message":"Agent run cancelled","recoverable":true}
```
```json
{"type":"error","message":"Connection failed","recoverable":false}
```
An error occurred. `recoverable: true` means the agent may continue; `false` means the run should stop.

### activity
Broadcast whenever a run starts, waits for approval or finishes. Payload matches `getActivity`.

```json
{"type":"activity","bots":[...],"pendingApprovals":1,"generatedAt":"..."}
```

### rpc_response
```json
{"type":"rpc_response","id":"req-1","result":[{"id":"abc","title":"hello","messageCount":2,"createdAt":"...","updatedAt":"..."}]}
```
```json
{"type":"rpc_response","id":"req-2","error":{"message":"Session not found"}}
```
Response to an RPC request that included an `id`. The client correlates the response by `id`. On success the result is in `result`; on failure an `error` object is returned.

## Requests (TUI → gateway)

### prompt
```json
{"method":"prompt","params":{"text":"List Python files"}}
```
```json
{"method":"prompt","params":{"text":"Continue","sessionId":"abc123"}}
```
Send a user message to the agent. If `sessionId` is provided, the gateway resumes that session.

### cancel
```json
{"method":"cancel","params":{}}
```
Cancel the current agent run. The gateway will emit an `error` event with `recoverable: true`.

### RPC requests

RPC requests include a unique `id` so the gateway can return a matching `rpc_response` event.

#### listSessions
```json
{"id":"req-1","method":"listSessions","params":{}}
```
Returns a list of session metadata objects, newest first.

#### createSession
```json
{"id":"req-2","method":"createSession","params":{"title":"New chat"}}
```
Creates a new empty session and persists it. Returns the full session object.

#### loadSession
```json
{"id":"req-3","method":"loadSession","params":{"sessionId":"abc123"}}
```
Loads a session including its messages.

#### updateSession
```json
{"id":"req-4","method":"updateSession","params":{"sessionId":"abc123","title":"Renamed chat"}}
```
Updates a session's title.

#### deleteSession
```json
{"id":"req-5","method":"deleteSession","params":{"sessionId":"abc123"}}
```
Deletes a session. Returns `{"ok": true}` on success.

#### getSettings / updateSettings
```json
{"id":"req-6","method":"getSettings","params":{}}
{"id":"req-7","method":"updateSettings","params":{"default_model":"deepseek/deepseek-v4-flash"}}
```
Read or update the active configuration. The payload mirrors `~/.xiaoqiao/config.toml`
(snake_case, models keyed by alias); legacy camelCase keys such as `primaryModel`
are still accepted on write.

#### getActivity
```json
{"id":"req-8","method":"getActivity","params":{}}
```
Returns what every bot is doing right now:

```json
{
  "bots": [
    {"botId":"bot_1","state":"needs_you","runId":"run_x","sessionId":"s_1","groupId":null,
     "title":"本周竞品摘要","currentTool":"run_command","startedAt":"...",
     "lastFinished":{"runId":"run_w","title":"上周摘要","status":"done","endedAt":"..."}}
  ],
  "pendingApprovals": 1,
  "generatedAt": "..."
}
```

`state` is one of `needs_you` > `working` > `error` (a failure within five minutes) > `idle`.
The same payload is broadcast as the `activity` event whenever a run changes state.

#### draftRoutineFromRun
```json
{"id":"req-9","method":"draftRoutineFromRun","params":{"runId":"run_x"}}
```
Builds a routine draft from a finished run: `{runId, botId, name, prompt, steps, schedule, hasSteps}`.
The steps are *context* for the next run, not a replay of the original tool arguments.

> RPC requests are implemented by the **WebSocket gateway** (`gateway/ws_server.py`). The legacy stdio gateway only supports `prompt` and `cancel`.

## Example Conversation

```
TUI → {"method":"prompt","params":{"text":"echo hello"}}

TUI ← {"type":"text_delta","delta":"Let"}
TUI ← {"type":"text_delta","delta":" me"}
TUI ← {"type":"text_delta","delta":" run"}
TUI ← {"type":"text_delta","delta":" that..."}
TUI ← {"type":"turn_end","reason":"tool_calls"}
TUI ← {"type":"tool_call_start","callId":"call_1","name":"bash","arguments":"{\"command\":\"echo hello\"}"}
TUI ← {"type":"tool_execution_start","callId":"call_1","name":"bash"}
TUI ← {"type":"tool_execution_end","callId":"call_1","name":"bash","ok":true,"exitCode":0}
TUI ← {"type":"text_delta","delta":"Done!"}
TUI ← {"type":"turn_end","reason":"complete"}
TUI ← {"type":"done"}
```
