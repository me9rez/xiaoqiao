# Agent 实现重构技术方案

> 状态：**阶段零/一/二已完成**（迁移到 `create_harness_agent`）；阶段三及以后待办
> 范围：`python/src/coding_agent/` 的 agent 运行时层（runtime / gateway）
> 相关文档：`docs/proposal.md`（原始设计，部分内容已过时）、`docs/protocol.md`

---

## 0. 实施结果（2026-09-19）

迁移已完成并通过真实 DeepSeek API 验证。**§4 的问题清单保留作为改造前的问题记录**；本节描述改造后的实际状态。

### 0.1 代码变化

| 变化 | 文件 | 说明 |
|------|------|------|
| 新增 | `agent_runtime.py`（396 行） | `create_harness_agent` 构造 + 事件翻译 + 审批往返 |
| 新增 | `tool_events.py`（121 行） | `ToolEventMiddleware`（原 `loop.py` 中抽出）+ 结果规范化 |
| 新增 | `turn_runner.py`（105 行） | 两会话网关共享的编排层（消除 P1-3 重复） |
| 删除 | `loop.py`（382 行） | 遗留自研 loop |
| 删除 | `workflow_loop.py`（482 行） | 自研 HITL 轮次编排 |
| 删除 | `test_workflow_thinking_attach.py`（151 行） | 针对已删除代码的回归测试 |
| 改写 | `gateway/{ws_,}server.py` | 均改为经 `TurnRunner` 走 harness |

净减约 1100 行。

### 0.2 问题清单处置

| # | 问题 | 状态 |
|---|------|------|
| P0-1 | 默认路径无 compaction | ✅ 已修复。**注意**：首轮实现只传了 `max_context_window_tokens`，而 harness 要求 `max_output_tokens` 同时存在才构建策略，实际仍处于关闭状态；现两者都传并有回归测试 |
| P0-2 | `framework_session` 死管线 | ✅ 已真正使用；实测同一会话文件从 105 字节空壳变为 4205 字节含 6 条消息 |
| P0-3 | `_ensure_not_duplicate` 空操作 | ✅ 随 `loop.py` 删除而消失 |
| P0-4 | `_FakeClient` 协议不合规 | ✅ 已补齐 `additional_properties`（`isinstance(..., SupportsChatGetResponse)` 为 True） |
| P0-5 | **MCP 服务器全部无法连接** | ✅ 已修复。`agent-framework-core` 只在其未使用的 `all` extra 下声明 `mcp<2`，解析到 mcp 2.x 后框架读取已被重命名的 `protocolVersion` 而崩溃；已在 pyproject 固定 `mcp>=1.21.1,<2` |
| P1-1 | 两套 loop 分叉 | ✅ 两文件均删除，thinking 解析统一在 `agent_runtime` |
| P1-2 | `use_workflow` 默认值取反 | ✅ 分流逻辑消失 |
| P1-3 | 网关层重复 | ✅ 编排逻辑收敛到 `TurnRunner` |
| P2-2 | async-iterable 静默吞结果 | ✅ 改为抛 `TypeError`（`tool_events.extract_tool_result`） |
| P3-1 | `ToolExecutionDeltaEvent` 从未发射 | ⏳ 仍未发射，待决（实现或删除） |
| P2-1 | 私有 API 依赖 | ⏳ 未处理（阶段五） |
| P2-3 | 测试覆盖倒挂 | ⏳ 部分改善（新增 runtime + compaction 单测），工具层仍待补 |
| P3-2 | 无 workspace 限制 | ⏳ 未处理 |

### 0.3 真实 API 验证记录

以下均在**真实 DeepSeek API**（`deepseek/deepseek-v4-flash`）上跑通：

| 场景 | 结果 |
|------|------|
| 纯文本对话 | ✅ `17 × 23 = 391` |
| 工具轮次 | ✅ `function_call` → `function_result` → 最终回答 |
| 审批暂停 | ✅ `tool_approval_request` 事件 + 会话保持 |
| 审批通过 | ✅ 工具**在批准后才执行** |
| 审批拒绝 | ✅ 工具**不执行**，模型说明已拒绝 |
| 多轮上下文 | ✅ 会话累积（8 条消息），跨轮次保持 |
| 网关 e2e | ✅ `WsGatewayServer._handle_prompt` → `_resume_approval` 全链路 |
| 事件完整性 | ✅ text/thinking/tool_call_start/tool_execution_start/_end/usage/turn_end/done |
| **skills 接入** | ✅ `SkillsProvider` 出现在 agent 的 `context_providers` 中 |
| **MCP 接入** | ✅ 起真实 stdio MCP 服务器（`mcp.server.fastmcp`），模型调用 `probe_echo` 并取回 `echo:banana` |
| **compaction 生效** | ✅ `compaction_strategy=ContextWindowCompactionStrategy` 且 `CompactionProvider` 已装配 |

前端事件契约未变（`web/src/types/gateway.ts` 无需改动），web 测试 18/18 通过。

### 0.4 关键设计决定

1. **框架 `AgentSession` 是对话状态的唯一权威**。它维护 `tool_call`/`tool_result` 配对——OpenAI 兼容 API 强制要求这个配对，自己重建消息列表会触发 400。JSONL 转录只是它的投影，用于历史与 UI。
2. **事件层保留自研**。框架流是 `AgentResponseUpdate`，没有等价于 `text_delta` 的细粒度契约；官方 `ConsoleObserver` 面向 Textual，不能服务本项目的 gateway 协议。
3. **`ToolEventMiddleware` 继续使用**。框架流不含工具生命周期，且实测 harness **合并**而非替换传入的中间件链（`[ToolApprovalMiddleware, MessageInjectionMiddleware, ToolEventMiddleware]`）。
4. **不再需要 `_FakeClient`**。它是无 key 时的降级路径，但不符合 `SupportsChatGetResponse`，导致工具轮次不执行；改用真实 API 测试后已无价值。

### 0.5 已知遗留

- `FileSystemAgentFileStore` 带 `ExperimentalWarning`（框架标注 API 可能变动）。
- 审批恢复时框架会打印 `Ignored an approval response ... occurrence identity` 警告。实测**审批语义正确**（通过则执行、拒绝则不执行、均只执行一次），该警告不影响行为，疑为框架内部重放检查，未深究。
- 网关实例内的 `_runtimes` 缓存未随会话删除而清理（长跑进程会缓慢增长）。
- `mcp<2` 为**临时约束**：`agent-framework-core` 一旦支持 mcp 2.x（`protocol_version`），应解除该上界。

### 0.6 本轮修正的两个自身缺陷（复盘）

首轮提交（`adacc30`）声称"compaction 已由 harness 接管"，**该声明当时不成立**：

1. **compaction 实际仍关闭**。`_assemble_compaction` 仅当 `max_context_window_tokens` 与
   `max_output_tokens` **同时**提供时才构建策略，否则静默禁用。首轮只传了前者，
   `compaction_strategy` 为 `None`、也没有 `CompactionProvider`。现已两者都传（含
   `maxTokens` 越界时的钳制），并加了 5 个回归测试。
2. **MCP 完全不可用**。依赖升级把 `mcp` 提到 2.2.0，而 `agent-framework-core` 的 MCP
   集成读取 `initialize_result.protocolVersion`（2.x 已更名为 `protocol_version`），
   任何 MCP 服务器连接都会抛 `AttributeError`。框架只在未安装的 `all` extra 下声明
   `mcp<2`，所以解析器不会自动兜住。已在 `pyproject.toml` 固定 `mcp<2`，并用真实
   stdio MCP 服务器验证模型能成功调用其工具。

**教训**：这两处都是"配置看起来生效、实为零效果"的静默失效——只靠"import 通过 + 单测绿"
无法发现，必须断言到最终对象的实际属性（`agent.compaction_strategy`、
`agent.mcp_tools` + 一次真实工具调用）。后续改动建议沿用这一断言方式。

---

## 1. 背景与目的

当前 agent 运行时存在**两套并行的实现**（`loop.py` 与 `workflow_loop.py`），且在演进中已经分叉。默认执行路径（`workflow_loop=True`）反而是能力较弱的一侧，并伴随若干**已实测确认的正确性缺陷**与**死代码管线**。

本文档的目标：

1. 给出**已核实**的问题清单，标注严重级别与证据来源。
2. 区分**已实测确认**与**仅源码推断、尚未实测**的结论（不夸大确定性）。
3. 给出分阶段改造方案，每一步都带可执行的验证方式。
4. 明确列出**当前不建议做**的事，避免过度重构。

---

## 2. 结论摘要

| # | 问题 | 级别 | 证据强度 |
|---|------|------|----------|
| 1 | 默认路径无上下文压缩（compaction） | **P0** | 已核对源码 |
| 2 | `framework_session` 死管线，每次会话产生孤儿文件 | **P0** | 已实测（磁盘 47 : 14） |
| 3 | `_ensure_not_duplicate` 是空操作 | **P0** | 已实测 |
| 4 | 两套 loop 分叉，默认路径 thinking 解析为子集 | **P1** | 已核对源码 |
| 5 | `use_workflow` 默认值取反 | **P1** | 已核对源码 |
| 6 | 网关层近乎复制粘贴（371 / 857 行） | **P1** | 已核对源码 |
| 7 | 36 处私有 API 依赖，其中 100% 可走公开 API | **P2** | 已实测（23/23 同对象） |
| 8 | `_extract_tool_result` 静默吞掉 async-iterable 结果 | **P2** | 已实测 |
| 9 | 测试覆盖与风险倒挂（工具层 908 行几乎无测试） | **P2** | 已核对 |
| 10 | `ToolExecutionDeltaEvent` 定义了但从未发射 | **P3** | 已核对 |
| 11 | 无 workspace 限制 | **P3** | 已核对 |
| 12 | `_FakeClient` 不符合 `SupportsChatGetResponse`，致无 key 时工具轮次不执行 | **P0** | 已实测 |

**根因**：不是"自研 loop"本身有问题，而是**自研编排层与框架原生能力重叠，且重叠部分没有清晰的边界**——既有框架已经提供的（会话状态、审批、压缩），又自己实现了一套，结果两套都只做了一半。

**关键发现（§6）**：框架的 `create_harness_agent` 正是为解决这批问题而设计的官方方案，且**本项目已安装的版本即可用**。`docs/proposal.md` 当初否决它的理由（事件粒度过粗）在实测中不成立。因此改造主线应为**迁移到官方 harness**，自研部分收敛为事件层。

---

## 3. 现状事实核对

以下数字均为本次核查实测，可作为改造前后的对照基线。

### 3.1 代码规模

| 文件 | 行数 | 说明 |
|------|------|------|
| `tools/coding_tools.py` | 908 | 工具实现 |
| `gateway/ws_server.py` | 857 | WebSocket 网关（现役） |
| `session.py` | 494 | JSONL 会话持久化 |
| `workflow_loop.py` | 482 | **默认** loop |
| `loop.py` | 382 | 遗留 loop |
| `gateway/server.py` | 371 | stdio 网关（遗留） |
| `events.py` | 151 | 自研事件定义 |
| `compaction.py` | 75 | 压缩策略 |
| `framework_session.py` | 71 | 框架会话桥接（**死代码**） |

### 3.2 依赖框架的方式

```
私有 import（下划线模块）   : 36 处（src 25 + tests 11）
公开 import（顶层导出）     :  4 处
分布模块：_types(11) / _tools(5) / _skills(4) / _clients(2) / _middleware(2) / _compaction(1)
```

**关键事实**：核查了项目实际使用的 23 个符号，**23/23 均可从 `agent_framework` 顶层公开导入**，且 `is` 判定为同一对象。

```
agent_framework 公开导出总数: 331
被核对符号中公开可用的     : 23/23
其中与私有路径同一对象的   : 23/23
```

包括直觉上以为必须走私有的：`FunctionInvocationContext`、`ContextWindowCompactionStrategy`、`apply_compaction`、`SupportsChatGetResponse`、`MCPStdioTool`、`SkillsSourceContext`。

唯一真正无法通过换 import 解决的是**属性级**私有访问：`tests/unit/test_skills.py` 中的 `provider._source`。

### 3.3 当前是否在用框架 `Agent`

**是**。`loop.py:202`、`workflow_loop.py:334/346` 均实例化 `agent_framework.Agent`，工具调用循环由框架的 `FunctionInvocationLayer` 驱动。自研部分为：细粒度事件层、工具事件中间件、审批轮次编排。

---

## 4. 问题详述

### P0-1 默认路径无上下文压缩

**事实**：`compaction_max_tokens` 只传给 `run_coding_agent`：

```
main.py:246        compaction_max_tokens=max_tok,
server.py:297      compaction_max_tokens=max_tok,
ws_server.py:757   compaction_max_tokens=max_tok,
```

而 `run_coding_workflow` 的签名中**根本没有 compaction 参数**（`workflow_loop.py:259-272`）。由于 `Settings.workflow_loop` 默认为 `True`（`settings.py:83`），默认路径的长会话将一路增长到 context window 上限。

**影响**：长会话必然触顶失败，且不是渐进降级而是硬失败。

**修复方向**：`agent.run()` 原生支持 `compaction_strategy=`，无需自研。或短期先把 `compaction_max_tokens` 接入 workflow 路径。

---

### P0-2 `framework_session` 死管线

**事实**：`run_coding_workflow` 收下会话参数后直接丢弃：

```python
async def run_coding_workflow(..., framework_session: Any | None = None):
    """Run the single-agent coding workflow with native framework HITL."""
    del framework_session          # ← 丢弃
```

但调用方假设它在工作——`framework_session` 在 `src/` 中出现 **47 次**：两个网关都做 `get_or_create` → 传入 → 放进 `_pending_approvals` → `save_framework_session()` 落盘。

**实测后果**（本机 `.coding-agent/sessions/`）：

```
framework_session 文件数: 47
jsonl 真实会话文件数:     14
```

多出的 33 个孤儿文件内容为空壳：

```json
{"type": "session", "session_id": "000b5ecdde5d", "state": {}}
```

105 字节，状态为空。`delete_framework_session()`（`framework_session.py:56`）**定义了但从未被调用**，因此永不回收。

**修复方向**：二选一——(a) 让 workflow 真正接收并使用 `session=`；(b) 整条管线删除。**建议先评估 (b)**：在 P0-1 的原生 compaction 迁移完成前，(a) 等于把一个未验证的状态机引入主路径。

---

### P0-3 `_ensure_not_duplicate` 是空操作

**事实**（`loop.py:374-382`）：

```python
def _ensure_not_duplicate(messages: list[Any], msg: Any) -> None:
    """Skip appending if the message already exists (by identity or id)."""
    if msg in messages:
        return
    ...
```

返回 `None`，而调用方无条件追加：

```python
for msg in response.messages:
    _ensure_not_duplicate(messages, msg)
    messages.append(msg)      # ← 无论是否为重复都会追加
```

**实测**：

```
return value when already present: None
return value when absent:          None
before=1 after=2
DUPLICATE APPENDED? True
```

**影响**：函数承诺的去重保护不存在。当前是否实际产生重复消息取决于 `response.messages` 是否与 `messages` 有交集——需在修复时一并确认。

**修复方向**：改为返回 `bool` 并由调用方据此跳过；或删除函数消除误导。倾向后者（若确认无需去重）。

---

### P1-1 两套 loop 分叉

**事实**：两文件仅共享一个同名函数 `_extract_thinking`，且实现已分叉：

| | `loop.py` | `workflow_loop.py` |
|---|---|---|
| `_extract_thinking` 行数 | 61 | 35 |
| `content_block_delta` 分支 | ✅ | ❌ 缺失 |
| `rtype == "thinking"` 分支 | ✅ | ❌ 缺失 |
| `_process_update` / `_process_agent_update` | 有 | 有（另一份） |
| thinking 附加逻辑 | 内联 | `_attach_thinking` |

即**默认路径（workflow）的 raw thinking 解析是遗留路径的严格子集**。凡 thinking 仅出现在 `raw_representation` 的 provider，在默认路径下会丢失思考内容。

> ⚠️ **待确认**：`_process_update` 中另有 `contents` 分支兜底，实际是否丢失取决于 provider 走哪条路径。**尚未用真实 API key 复现**，不应据此断言线上正在丢失。

`workflow_loop.py:13` 的注释解释了为何不用 `ToolApprovalMiddleware`（称其会剥掉原始 `function_call`），但见 P1-2。

---

### P1-2 `use_workflow` 默认值取反

**事实**：`Settings.workflow_loop` 默认 `True`（`settings.py:83`），但两处判定写成默认 `False`：

```python
server.py:255    use_workflow = bool(getattr(self._settings, "workflow_loop", False))
ws_server.py:693 use_workflow = bool(getattr(settings, "workflow_loop", False))
```

因属性必然存在，**当前无实际行为差异**，但反映"遗留路径才是默认"的过时心智模型，是 P1-1 的认知来源。

---

### P1-3 网关层重复

```
server.py     371 行（stdio，遗留）   ┐ 4 个同名方法：
ws_server.py  857 行（WebSocket，现役）┘ __init__ / _emit / _handle_prompt / _resume_approval
```

`_handle_prompt` 与 `_resume_approval` 的编排逻辑（拼 system prompt → 分流 workflow/legacy → 处理 `PendingApproval` → 存 session）在两侧近乎逐行对应。这部分逻辑**与传输方式无关**，属于可抽取的共享层。

`docs/protocol.md` 已写明协议为 websocket，`server.py` + `transport.py` 是遗留路径，但仍在 `main.py` 可达（不带 `--web` 时）。

---

### P2-1 私有 API 依赖

36 处私有 import。**并非被迫**——见 §3.2，全部有公开等价物。

**实际代价**：本次 `agent-framework` 1.9 → 1.19 升级中，`get_skills()` 新增必填参数即导致测试失败；`_copy_middleware_sequence` 的行为假设导致 middleware 崩溃（1 行修复）。公开 API 有 deprecation 过渡，私有 API 没有。

**修复方向**：机械替换为顶层导入，零行为变化。唯一需单独说明的是 `provider._source`——测试应改走公开行为而非探内部属性。

---

### P2-2 `_extract_tool_result` 静默吞结果

**事实**（`loop.py:107-111`）：

```python
if hasattr(result, "__aiter__"):
    return "", None, True
```

**实测**：

```
async-iterable result -> ('', None, True)
```

返回空文本 + `ok=True`——**既不报错也不返回内容**。

**当前影响范围**：`coding_tools.py` 中无任何工具返回 async generator（已核查，`yield` 计数为 0），故为**潜伏缺陷**而非现行 bug。

**修复方向**：改为抛出显式异常，避免将来有工具误用此路径时静默丢数据。

---

### P2-3 测试覆盖与风险倒挂

```
测试规模: 28 tests / 5 个文件
```

| 模块 | 行数 | 测试情况 |
|------|------|----------|
| `tools/coding_tools.py` | 908 | 仅 import 一个 `_ToolResult` |
| `gateway/ws_server.py` | 857 | 无 |
| `session.py` | 494 | 仅间接（序列化） |
| `workflow_loop.py` | 482 | 仅 `_attach_thinking` |
| `gateway/server.py` | 371 | 无 |

含 shell 执行、文件写入、审批门禁的 `coding_tools.py` 基本裸奔。**实证**：本次修复的 middleware 崩溃（默认路径必崩）在修复前 28 个测试**全绿**。

---

### P3-1 `ToolExecutionDeltaEvent` 从未发射

事件在 `events.py` 定义，两个网关都实现了序列化分支（`server.py:61`、`ws_server.py:134`），但**没有任何构造点**。设计的"工具流式输出"能力未实现。

### P3-2 无 workspace 限制

`Path(path).resolve()` 后无 jail 校验，`read_file` 可读任意路径；`run_command` 在 POSIX 走 `create_subprocess_shell`，`cwd=os.getcwd()` 而非会话 workspace。写操作有 `always_require` 审批兜底，**读操作无审批**。

此为设计取舍而非缺陷，但需**显式决策并写入文档**。

---

### P0-4 `_FakeClient` 不符合协议

**事实**（`settings.py:269`）：`_FakeClient` 缺少协议要求的数据成员。

**实测**：

```
isinstance(_FakeClient(), SupportsChatGetResponse)                    -> False
（补上 additional_properties 数据成员后）                              -> True
```

**影响**：函数调用层把不符合协议的 client 视为**不支持工具**，因此**无 API key 时工具轮次完全不执行**。这解释了 `main.py --test` 模式下工具循环不生效的现象。

**为什么是 P0**：它是本文档多数验证的前置条件——在修复前，任何依赖工具轮次的验证（包括 §6 的 harness 迁移验证与阶段三 HITL 验证）都无法在无 key 环境下进行。

**修复方向**：补 `additional_properties: dict = {}` 类属性，使其满足 `SupportsChatGetResponse`。

---

## 5. 根因分析

```
        ┌─────────────────────────────────────────┐
        │  agent-framework 1.9 → 1.19 快速演进      │
        │  （会话/审批/压缩逐步成为原生能力）        │
        └────────────────┬────────────────────────┘
                         │
        早期：自研编排（因为框架没有）
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │  两套并行实现，职责重叠但边界不清          │
        │  · loop.py        遗留，能力完整          │
        │  · workflow_loop  默认，能力较弱          │
        └────────────────┬────────────────────────┘
                         │
        ┌────────────────┴────────────────────────┐
        ▼                                         ▼
  能力缺口（无 compaction）              死代码（framework_session）
  显式缺陷（去重空操作）                认知漂移（默认值取反）
```

**核心判断**：项目**不是**"不该自研 loop"。§6 会说明事件层是有真实需求的。问题在于**自研层与框架原生能力的重叠区域没有划清边界**——凡是框架已经提供的，就应直接用原生的，自研只保留框架确实不提供的部分。

**补充（§6 实测）**：框架原生 harness（`create_harness_agent`）已覆盖本文档 P0-1 / P0-2 / P1-1 / P1-2 / P3-2 五项问题，且允许自研事件中间件叠加。

---

## 6. 框架原生 Harness 方案评估

**触发**：`docs/proposal.md:35` 以"streaming 事件粒度太粗"为由明确否决了 `create_harness_agent`。核查 Microsoft 官方示例
`python/samples/02-agents/harness/build_your_own_claw/`（含 `claw_step04_production_ready`）后，该理由需要重新评估。

### 6.1 官方示例的用法

官方 "production ready" 示例的核心是一次工厂调用：

```python
agent = create_harness_agent(
    client=client,
    name="ClawFinanceAssistant",
    agent_instructions=FINANCE_INSTRUCTIONS,
    tools=[get_stock_price, place_trade, *skills_tools],
    history_provider=InMemoryHistoryProvider(),
    file_access_store=access_store,
    file_memory_store=file_memory_store,
    skills_provider=skills_provider,
    background_agents=[research_agent],
    shell_executor=shell,
    auto_approval_rules=auto_approval_rules,
    context_providers=context_providers,
    mode_provider=AgentModeProvider(default_mode="execute"),
    default_options=default_options,
)
```

按官方 docstring，它自动装配：函数调用循环、每轮历史持久化、**上下文压缩**、TodoProvider、
AgentModeProvider（plan/execute）、FileMemoryProvider、FileAccessProvider、SkillsProvider、
BackgroundAgentsProvider、工具审批（含"不再询问"规则）、轮次循环。

### 6.2 实测结果

以下均在**本项目已安装的 1.19.0** 上运行核对，非文档推断：

| 结论 | 证据 |
|------|------|
| 所需符号全部公开导出 | 16/16 命中：`create_harness_agent` / `AgentModeProvider` / `FileAccessProvider` / `FileSkillsSource` / `AggregatingSkillsSource` / `DeduplicatingSkillsSource` / `MCPSkillsSource` / `InMemoryHistoryProvider` / `FileSystemAgentFileStore` / `tool` 等 |
| 返回类型是 `Agent` 子类 | `isinstance(agent, af.Agent) is True`，故现有 `agent.run(stream=True)` 用法不变 |
| 流式仍为细粒度 | 逐 chunk 产出：观察到两次独立 `type='text'` 与一次 `type='function_call'` |
| **本项目中间件可叠加** | 传入 `middleware=[ToolEventMiddleware(...)]` 后链为 `[ToolApprovalMiddleware, MessageInjectionMiddleware, ToolEventMiddleware]` —— **合并而非替换** |
| 中间件行为不变 | 驱动该中间件仍产出 `ToolCallStartEvent` / `ToolExecutionStartEvent` / `ToolExecutionEndEvent` |
| 接受本项目真实工具 | `create_coding_tools()` 的 17 个 `FunctionTool` 直接传入成功 |
| 原生会话 | `agent.create_session() -> AgentSession` |

### 6.3 与本文档问题清单的对应

| 本文档问题 | harness 原生能力 |
|---|---|
| P0-1 默认路径无 compaction | `max_context_window_tokens` / `before_compaction_strategy` / `after_compaction_strategy` |
| P0-2 `framework_session` 死管线 | `agent.create_session()` + `agent.run(..., session=...)` |
| P1-1 两套 loop 分叉 | 单一工厂产出，无需自研编排 |
| P1-2 `use_workflow` 默认值取反 | 不再需要 workflow/legacy 分流 |
| P3-2 无 workspace 限制 | `file_access_store` + `LocalShellTool(confine_workdir=True)` |

### 6.4 事件层：官方参考实现

官方 `harness/console/` 包给出的正是细粒度事件层参考实现：

```python
class ConsoleObserver:
    async def on_response_update(ux, update, agent, session): ...
    async def on_content(ux, content, agent, session): ...
    async def on_text(ux, text, agent, session): ...
    async def on_stream_complete(ux, agent, session) -> list[FollowUpAction] | None: ...
```

配套 observer 覆盖 tool call、审批、reasoning、usage、error、web search、planning。

两点值得注意：

1. **thinking 走原生 content 类型**。`reasoning_display.py` 判定 `content.type in {"text_reasoning", "reasoning"}`，
   而非解析 `raw_representation`。对照：本项目 `loop.py._extract_thinking` 手写 61 行解析 OpenAI/Anthropic 原始结构
   （见 P1-1），官方做法明显更稳。
2. **HITL 往返有官方范式**。`ToolApprovalObserver` 在流中收集 `function_approval_request`，流结束后构造选择项
   （批准一次 / 永久批准该工具 / 永久批准该参数 / 拒绝），续跑时用
   `request.to_function_approval_response(approved=...)` 或 `create_always_approve_tool_response(...)` 注入。
   本项目 `resume_coding_workflow` 做的是同一件事，但是自研。

### 6.5 差异与风险

1. **`_FakeClient` 不符合协议**（实测）：`isinstance(_FakeClient(), SupportsChatGetResponse)` 为 `False`，
   根因是缺少协议要求的 `additional_properties` 数据成员；补上后为 `True`。
   这解释了一件此前困惑的事：**无 API key 时工具轮次不执行** —— 函数调用层把不合规 client 当作不支持工具。
   与 harness 无关，是既有缺陷，但会阻碍无 key 验证。
2. harness 自带 `ToolApprovalMiddleware` 且**要求 session**（实测报错 `ToolApprovalMiddleware requires an AgentSession.`）。
   采用 harness 即必须传 session，与 P0-2 修复方向一致。
3. `FileSystemAgentFileStore` 带 `ExperimentalWarning`（实测），API 可能变动。
4. 官方示例基于 `FoundryChatClient`；本项目用 `OpenAIChatCompletionClient`。harness 参数类型为
   `SupportsChatGetResponse`，理论上通用，但**未用真实 client 端到端验证**。

### 6.6 评估结论

`proposal.md` 否决 `create_harness_agent` 的"事件粒度太粗"理由，在 1.19.0 上**看起来不成立**：
流式仍是逐 chunk 的，自研中间件可叠加，官方 console 包本身就示范了更完整的细粒度事件层。

> 证据强度：**源码 + 运行实测**。但完整工具轮次与真实 provider 未验证（见 §9）。

建议将改造主线从"合并两套自研 loop"调整为"**迁移到 `create_harness_agent`，保留并简化事件层**"。

---

## 7. 改造方案

### 7.1 保留什么（明确不动）

| 组件 | 保留理由 |
|------|----------|
| `events.py` 事件层 | 仍有价值：它是**面向本项目 gateway/前端协议**的稳定契约。官方 `ConsoleObserver` 是面向 Textual 控制台的，不能直接复用。改造方向是让其 content 解析对齐原生类型（§6.4），而非删除 |
| `ToolEventMiddleware` | 实测可与 harness 中间件链**叠加**（§6.2），保留成本低 |
| `tools/coding_tools.py` 工具实现 | 业务逻辑，与框架无关 |

### 7.2 分阶段计划

> 主线已由 §6 评估调整为：**向 `create_harness_agent` 迁移**，而非在自研 loop 之间做合并。

#### 阶段零：前置修复（其他一切验证的前提）

| 任务 | 文件 | 说明 |
|------|------|------|
| T0.1 | `settings.py` | `_FakeClient` 补 `additional_properties`，使其满足 `SupportsChatGetResponse`。**实测这是无 key 时工具轮次不执行的原因**（§6.5-1），会阻塞后续所有无 key 验证 |

**验证**：
```bash
uv run python -c "
import agent_framework as af
from coding_agent.settings import _FakeClient
print(isinstance(_FakeClient(), af.SupportsChatGetResponse))  # 应为 True
"
```

#### 阶段一：止血（低风险，可独立完成）

| 任务 | 文件 | 说明 |
|------|------|------|
| T1.1 | `loop.py` | `_ensure_not_duplicate` 改返回 `bool` 并让调用方据此跳过；若确认无需去重则删除 |
| T1.2 | `loop.py` | async-iterable 分支改为抛显式异常 |
| T1.3 | `settings.py` / 两网关 | 统一 `workflow_loop` 判定，消除 `getattr(..., False)` 取反 |
| T1.4 | `gateway/*.py` | **决策** `framework_session` 去留（随阶段二一并处理） |

**验证**：
```bash
cd python
uv run pytest -q
uv run ruff check src/ tests/
uv run pyright src/
```

#### 阶段二：迁移到 `create_harness_agent`（主线）

| 任务 | 说明 |
|------|------|
| T2.1 | 用 `create_harness_agent` 替换 `workflow_loop._run_workflow` 的 Agent 构造，保留 `ToolEventMiddleware` 与事件层 |
| T2.2 | 传入 `max_context_window_tokens`（或其他 compaction 参数）解决 P0-1；删除自研 `compaction.py` 降级路径 |
| T2.3 | 用 `agent.create_session()` + `agent.run(..., session=...)` 解决 P0-2；**删除** `framework_session.py` 及其 47 处引用 |
| T2.4 | 对齐事件层的 thinking 解析到原生 `content.type`（参照官方 `reasoning_display.py`），消除 `loop.py` / `workflow_loop.py` 的分叉 |
| T2.5 | 评估 `loop.py` 是否仍有存在必要；若仅剩遗留 stdio 网关依赖，随阶段四一并移除 |

**决策点**：T2.1 之后应以 harness agent 为唯一 agent 构造入口。两套自研 loop 的合并**不再是独立目标**——它们随迁移自然消失。

**验证**：
```bash
uv run pytest -q
# 新增：thinking 原生 content 类型单测
# 新增：compaction 触发单测（或确认由 harness 接管）
python -m coding_agent.main --test "prompt"   # 需真实 API key
```

#### 阶段三：HITL 收敛（**前置验证，未验证不得动手**）

`workflow_loop.py:13` 声称 `ToolApprovalMiddleware` 会剥掉原始 `function_call`。**源码阅读表明该理由在当前版本上已不成立**：

```python
def _remove_approval_requests(messages, remove_ids):
    filtered = [
        content for content in message.contents
        if content.type != "function_approval_request" or id(content) not in remove_ids
    ]
```

只过滤 `function_approval_request`，**不触碰 `function_call`**。且实测 `ToolApprovalMiddleware` 确实由 harness 自动装配（§6.2）。

> ⚠️ **未能端到端复现**：受 §6.5-1 的 `_FakeClient` 缺陷阻塞，工具轮次未执行，`queued_approval_requests` 为 0。
> **T0.1 修复后需重新验证**，之后才能断言原生方案可用。

**官方范式**（`console/observers/tool_approval.py`）：流中收集 `function_approval_request` → 流结束构造选项
（批准一次 / 永久批准该工具 / 永久批准该参数 / 拒绝）→ 续跑时注入
`request.to_function_approval_response(approved=...)` 或 `create_always_approve_tool_response(...)`。

**任务**：
| 任务 | 说明 |
|------|------|
| T3.1 | **用真实 API key 验证**原生 `ToolApprovalMiddleware` 的审批 → 恢复完整往返 |
| T3.2 | 若可行：`workflow_loop` 的 `_strip_approval_wrappers` / `_collect_approval_requests` / 轮次循环塌缩为中间件配置 |
| T3.3 | 若不可行：保留自研，但**更新 `workflow_loop.py:13` 的注释**，说明当前真实失效原因 |

**验证**：真实 key 下的审批往返集成测试；`--test` 模式的 `PENDING_APPROVAL` / `SESSION_BEFORE_RESUME` 输出。

#### 阶段四：网关合并

| 任务 | 说明 |
|------|------|
| T4.1 | 抽出 transport-agnostic 的编排层（`_handle_prompt` / `_resume_approval` 共享逻辑） |
| T4.2 | 评估并移除 stdio 遗留路径（`server.py` + `transport.py`）及 `main.py` 中的分支 |
| T4.3 | 决定 `ToolExecutionDeltaEvent`：实现或删除（连同两处序列化分支） |

**验证**：
```bash
cd web && pnpm test:unit && pnpm type-check && pnpm build
# 网关集成测试（当前缺失，需新建）
```

#### 阶段五：私有 API 收敛

| 任务 | 说明 |
|------|------|
| T5.1 | 36 处私有 import 替换为顶层公开导入（机械替换，零行为变化） |
| T5.2 | `test_skills.py` 的 `provider._source` 改走公开行为断言 |
| T5.3 | 若确有必须走私有的符号，集中到 `_framework_compat.py` 适配层，升级时只改一处 |

**验证**：
```bash
uv run pytest -q            # 应完全无变化
uv run ruff check src/ tests/
# grep 确认私有 import 归零（或仅剩适配层）
```

#### 阶段六：测试补齐

优先级按"风险 × 无覆盖"排序：

| 优先级 | 目标 | 用例方向 |
|--------|------|----------|
| 高 | `tools/coding_tools.py` | `_edit_file` 唯一匹配校验、`run_command` 超时/退出码、审批模式解析 |
| 高 | 网关编排层 | 审批流转、session 持久化、workflow/legacy 分流 |
| 中 | `session.py` | 序列化往返、索引一致性 |
| 中 | `compaction.py` | 触发阈值、降级路径 |

---

## 8. 明确不做的事

| 不做 | 理由 |
|------|------|
| 删除事件层改用官方 `ConsoleObserver` | 官方版本面向 Textual 控制台，不能直接服务本项目 gateway/前端协议。应借鉴其 content 解析方式，而非替换（§7.1） |
| 在 T0.1 与阶段三验证前迁移 HITL | 未验证的状态机引入主路径，风险高于收益 |
| 为私有 import 建复杂抽象 | 36 处均可直接替换为公开导入，无需抽象层 |
| 顺手"优化" `docs/proposal.md` | 该文档已过时（仍描述无 `Agent` 的自研 loop、端口 8765），但更新属独立任务。**注意其 §"为什么不用 create_harness_agent" 的结论已被 §6 推翻，应优先修正以免误导后续开发** |

---

## 9. 未验证事项清单（须在实施前确认）

| # | 事项 | 为何未确认 | 影响 |
|---|------|-----------|------|
| 1 | 完整工具轮次端到端 | 受 `_FakeClient` 缺陷阻塞（T0.1）；无真实 key | 阻塞阶段三与迁移验证 |
| 2 | 原生 `ToolApprovalMiddleware` 审批往返 | 同上，`queued_approval_requests` 未触发 | 决定阶段三可行性 |
| 3 | `create_harness_agent` + `OpenAIChatCompletionClient` 真实运行 | 未用真实 key 跑通 | 迁移主线的最大未知 |
| 4 | workflow 路径是否真在丢 thinking | 未用真实 provider 复现 | P1-1 的实际严重度 |
| 5 | `_ensure_not_duplicate` 失效是否已产生重复消息 | 需观察真实 `response.messages` 与 `messages` 交集 | P0-3 实际影响面 |
| 6 | 47 个孤儿文件是否曾被旧版本读取 | 无历史运行时记录 | T1.4 决策（删 vs 接活） |
| 7 | 1.9.0 时代私有 import 是否曾属必需 | PyPI 连接失败，旧版本 venv 未建成 | 影响对历史决策的评价（不影响改造） |

---

## 10. 验收标准

阶段零/一完成后：

- [ ] `_FakeClient` 满足 `SupportsChatGetResponse`
- [ ] `_ensure_not_duplicate` 不再是无操作，或已删除
- [ ] `workflow_loop` 默认值判定不再取反
- [ ] `uv run pytest` / `ruff check` / `pyright` 全绿

阶段二完成后：

- [ ] agent 构造走 `create_harness_agent` 单一入口
- [ ] 默认路径具备上下文压缩能力（原生）
- [ ] `framework_session.py` 及其 47 处引用已删除，无孤儿文件产生
- [ ] thinking 解析对齐原生 `content.type`，两套实现不再分叉
- [ ] 事件层与 gateway 协议无回归（前端测试通过）

阶段四/五完成后：

- [ ] 网关编排逻辑单一实现，无逐行对应副本
- [ ] 私有 import 归零（或仅剩显式适配层）
- [ ] `coding_tools.py` 与网关编排层有基本单测覆盖
- [ ] `docs/proposal.md` 中已过时的结论已修正

---

## 11. 附录：核查命令

本文档所有数据可用以下命令复现：

```bash
cd python

# 代码规模
Get-ChildItem src -Recurse -Filter *.py |
  ForEach-Object { [pscustomobject]@{ Lines=(Get-Content $_).Count; Path=$_.Name } } |
  Sort-Object Lines -Descending

# 私有 import 计数
Get-ChildItem src,tests -Recurse -Filter *.py |
  Select-String -Pattern '^\s*(from|import)\s+agent_framework\._' | Measure-Object

# 公开 vs 私有同一性验证
uv run python -c "
import importlib, agent_framework as af
for mod, name in [('agent_framework._types','Content'),
                  ('agent_framework._middleware','FunctionInvocationContext'),
                  ('agent_framework._compaction','apply_compaction')]:
    priv = getattr(importlib.import_module(mod), name)
    pub  = getattr(af, name)
    print(name, 'identical:', priv is pub)
"

# 孤儿文件
$d = Join-Path $env:USERPROFILE '.coding-agent\sessions'
\"framework_session: $((Get-ChildItem $d -Filter '*.framework_session.json').Count)\"
\"jsonl:             $((Get-ChildItem $d -Filter '*.jsonl').Count)\"

# 测试基线
uv run pytest --collect-only -q | Select-Object -Last 1

# --- §6 harness 相关 ---

# 1) 所需符号是否公开导出
uv run python -c "
import agent_framework as af
need = ['create_harness_agent','AgentModeProvider','FileAccessProvider',
        'FileSkillsSource','AggregatingSkillsSource','DeduplicatingSkillsSource',
        'MCPSkillsSource','InMemoryHistoryProvider','FileSystemAgentFileStore','tool']
missing = [n for n in need if n not in dir(af)]
print('missing:', missing or 'none')
"

# 2) 自研中间件能否与 harness 中间件链叠加
uv run python -c "
import agent_framework as af
from coding_agent.loop import ToolEventMiddleware
class C:
    additional_properties = {}
    def get_response(self, *a, **k): raise NotImplementedError
a = af.create_harness_agent(client=C(), name='P', agent_instructions='t',
                            middleware=[ToolEventMiddleware(lambda e: None)],
                            disable_web_search=True)
print([type(m).__name__ for m in a.middleware])
"

# 3) _FakeClient 协议合规性（T0.1）
uv run python -c "
import agent_framework as af
from coding_agent.settings import _FakeClient
print('compliant:', isinstance(_FakeClient(), af.SupportsChatGetResponse))
"

---

## 12. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-09-19 | 初稿，基于 `763782c` 核实现状 |
| 2026-09-19 | 补 §6 框架原生 Harness 评估：核查 Microsoft 官方 `build_your_own_claw` 示例并对本项目 1.19.0 实测；改造主线调整为迁移至 `create_harness_agent`；新增 P0-4（`_FakeClient` 协议不合规）与阶段零 |
| 2026-09-19 | **阶段零/一/二实施完成**：新增 §0 实施结果；`loop.py`/`workflow_loop.py` 删除，改为 `agent_runtime.py` + `tool_events.py` + `turn_runner.py`；真实 API 验证通过 |
| 2026-09-19 | **修正两处静默失效**（§0.6）：compaction 因缺少 `max_output_tokens` 实际未启用；MCP 因 `mcp` 解析到 2.x 而完全不可用，已固定 `mcp<2` 并用真实 MCP 服务器验证 |
