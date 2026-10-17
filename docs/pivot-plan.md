# 开发计划 v2：多 Bot 常驻运行时 + Bot 群聊（后端 + 前端）

> 状态：待评审 · 2026-10 · 基线：`f44ff33`（更名为 小巧/Xiaoqiao 之后）
> 配套：[product.md](product.md)（产品定位与路线图）、[design.md](design.md)（前端设计规范）
> 本文取代 2025 版 v1 方案（旧版基线 `22e225e`，其中 `loop.py` / `workflow_loop.py` 已被 harness 迁移删除）。旧版全文见 git 历史。

---

## 0. 交付定义

**本轮完成后应达到的状态**

1. 一次对话由「Bot」发起，而不是「当前唯一会话」：可建多个 Bot，人格、模型、工具白名单、工作目录彼此隔离。
2. **Bot 群聊可用**：一个群里多个 Bot 与用户共存；`@bot` 指定应答，Bot 回复里 @ 别的 Bot 触发下一跳；有跳数与防环上限。
3. 一次执行（Run）可由 Web、Telegram、Routine 三个入口触发；关掉浏览器，Run 继续跑完并落库。
4. 高风险工具审批落库、带 TTL、任一入口可批；**只有人类能批，Bot 之间不能互批**。
5. Web UI 与 Grok Bot 对齐：Bot/群切换 → 会话列表 → 对话（带作者与 @）→ 上下文面板。

**明确不做**（本轮或 12 个月内，见 product.md §3）

- 多租户 / 企业账号体系（SSO/SCIM、审计合规、按席位计费）；X DM；移动端；workflow builder；模型训练。
- 多 Agent 任务编排（product.md D3/D9）：群聊是**消息路由**，不是中心调度器；每个 Bot 独立跑自己的 Agent。

> 变更说明：此前一版曾把「Team Bots」理解为多租户，已更正。**群聊 = 一个主人的多个 Bot 同处一个线程、互相 @**，与账号体系无关；多租户回到远期评估。

---

## 1. 现状审计

### 1.1 后端

| 模块 | 现状（代码事实） | 问题 | 处置 |
|---|---|---|---|
| 执行入口 | `WsGatewayServer._handle_prompt`（`gateway/ws_server.py:652`）在连接处理函数内完成「解析会话 → 组装 prompt → 跑 agent → 存盘」 | 执行与连接耦合；无 WebSocket 连接时无人可触发 | 抽 RunManager |
| 单会话 | `self._session`（`ws_server.py:222`）作为兜底 | 单助手假设 | 删除 |
| 运行时缓存 | `TurnRunner.runtime_for`（`turn_runner.py:68`）按 `session_id` 缓存 `AgentRuntime` | 无 bot 维度；生命周期挂在 gateway 进程 | 改由 RunManager 持有，key = `(bot_id, session_id)` |
| 会话存储 | `session.py:82` JSONL + `sessions.json` 索引 | 无 `bot_id` / `group_id` / `run` 维度；并发写无保护 | 迁 SQLite，JSONL 降级为导出 |
| 协作模型 | 无 Group 实体；会话只属于单 Bot | 「几个助理同处一个线程」无从谈起 | 新增 groups / group_members / 路由 |
| 自动化 | `automation.py:12` 仅 JSON CRUD，`run_count` 从不递增 | 无调度器，routines 是壳 | 新增 scheduler |
| 人格 | `system_prompt.py:53` `_DEFAULT_INSTRUCTIONS` 写死「编程助手」 | 人格不进模型 | 拆 BASE_CONTRACT / persona |
| 工作目录 | `discover_project_context()` 默认 `Path.cwd()`（`system_prompt.py:242`） | 多 bot 串工作区 | 改 `bot.workspace` |
| 审批 | `self._pending_approvals` 内存 dict，按 `call_id`（`ws_server.py:228`） | 重启即丢；只能网页点；routine 触发必挂死 | 落库 + broker + TTL |
| 配置 | `settings.py` 全局单例 | 模型/审批策略无法按 bot 覆盖 | 全局默认 + bot 覆盖 |
| 工具 | `create_coding_tools()` 全局创建 | 工具集不可按 bot 裁剪 | 工具工厂接受白名单 |
| Skills/MCP | 启动时全局创建 | 无法按 bot 隔离 | 按 bot 组装 |

### 1.2 前端

| 模块 | 现状 | 问题 | 处置 |
|---|---|---|---|
| 布局 | `ChatView.vue`：Sidebar（会话）+ ChatHeader + RouterView + ContextPanel | 没有 Bot / 群概念 | 加 BotRail，Sidebar 拆为「群聊 + Bot 私聊」 |
| 会话列表 | `Sidebar.vue:67` 按 workspace 分组 | 会话不属于 bot / 群 | 按「群 / Bot」分区，再按时间排序 |
| 路由 | `/`、`/chat/:sessionId`、`/toolbox`、`/automation`、`/settings` | 没有 bot/group 维度 | 加 `/b/:botId`、`/g/:groupId`、`/approvals`、`/routines` |
| 状态 | `stores/sessions.ts` 拉全量 `listSessions` | 无 bots/groups/runs/approvals/artifacts store | 新增 5 个 store |
| 事件 | `gateway.ts` 全局事件流，按 `sessionId` 归位 | 群内多 Bot 并发回复无处安放 | 事件带 `groupId/botId/runId`，按 `replyTo` 排序 |
| 占位页 | channels / memory / security 均「开发中」 | Grok Bot 的核心页面空白 | 按 WBS 重写 |
| 设计 | 部分组件仍用旧变量与硬编码色（如 `#d9896d`） | 违反 design.md | 迁移到 `--color-*` token |

---

## 2. 目标架构

```
                   ┌──────────── channels/ ────────────┐
                   │ web(WS)   telegram   cli           │
                   └──────────────┬────────────────────┘
                                  │ InboundMessage
                                  ▼
┌──────────────────── runtime（常驻，单进程 asyncio） ────────────────────┐
│  BotRegistry   GroupRouter   SessionStore   RunManager                  │
│  ApprovalBroker   EventBus   Scheduler(20s tick)                        │
└───────────────┬────────────────────────────────────┬───────────────────┘
                │ RunRequest                          │ Event（run 级）
                ▼                                     ▼
        ┌───────────────┐                     ┌────────────────┐
        │ AgentRuntime  │                     │ 订阅者          │
        │ (每次 run 一个)│                     │ WS / Telegram  │
        └───────┬───────┘                     └────────────────┘
                │ tool calls
                ▼
        ┌───────────────┐
        │ Executor      │  local（默认） / docker（P4）
        └───────────────┘
```

**边界规则（代码评审必须拦）**

1. `runtime/` 不得 import `gateway/`；`gateway/` 只能调 runtime 公开方法。
2. `channels/` 只做协议翻译与收发，不含 agent 逻辑与 @ 路由。
3. 一次 Run 的审批、产物、用量必须落库；内存只做缓存。
4. 进程内不出现全局可变单例（settings 只读快照、工具按 bot 构造）。
5. **群聊路由只在 `GroupRouter` 里做**：解析 @、选收件人、跳数校验；Agent 本身不知道「群」的存在。

**进程模型**

- 单进程多 Bot：`AgentSession` 是内存对象，工具、EventBus、审批共享；隔离靠 `bot_id` + `bot.workspace`。
- 工具子进程（shell）由 Executor 统一管理，带 cwd/timeout/输出上限。
- 崩溃恢复：启动时扫 `runs` 中 `running/waiting_approval`，标记 `failed(interrupted)`；routine 按 `next_run_at` 补偿。

---

## 3. 核心概念与不变量

```
User（使用主体）
 ├── Bot（persona + model + tools 白名单 + workspace）
 └── Group（参与者 = 人 + N 个 Bot）
      ├── GroupMember（member_type: user | bot）
      ├── Channel / Thread（web / telegram …）
      ├── Session（bot × group/thread）        ← 每个 Bot 自己的上下文
      ├── Run（一次执行）                      ← 状态机 + 事件 + 审批
      ├── Routine（定时/事件）                 ← 触发 Run
      ├── Memory（facts + 摘要，按 bot × 人）
      └── Artifact（run 产物）
```

| # | 不变量 | 违反后果 |
|---|---|---|
| I1 | Bot 是唯一配置边界（人格/模型/工具/工作目录） | 多 bot 配置串味 |
| I2 | Run 是唯一执行单位，拥有状态机与 `run_id` | 渠道/routine 无法接入 |
| I3 | `AgentSession` 是对话状态权威，DB 只存投影与快照 | `tool_call/tool_result` 配对断裂 |
| I4 | 审批是 run 级、持久、可跨入口；**只有人类可批** | Bot 互批，审批形同虚设 |
| I5 | 所有可观测副作用（审批/产物/用量）落库 | 重启不可恢复 |
| I6 | 工作目录来自 `bot.workspace` | 多 bot 共享 cwd 互相污染 |
| I7 | **群聊共享消息流，但每个 Bot 的 Session 独立** | 把多 Bot 的工具调用混进一份上下文，模型会错乱 |
| I8 | **路由是确定性的**：@ 决定收件人，默认 Bot 兜底；跳数上限在 runtime 强制 | Bot 互 @ 死循环、账单爆炸 |
| I9 | **群内回复按 `reply_to` 串行落位**，不按到达顺序 | 多 Bot 并发时消息顺序不可读 |

Run 状态机：

```
queued → running → waiting_approval → running → done
              └────────────► failed / cancelled
```

- 同一 `session_id` 同时只允许一个 `running/waiting_approval`，其余 `queued`（FIFO）。
- 同一 `group_id` 的回复按 `reply_to` 分桶串行；不同 Bot 的 run 可并发执行，但**发出**有序。
- `cancel` 设置标记，在工具边界检查，不强制杀线程；`waiting_approval` 取消视为 `cancelled`。

---

## 4. 数据模型

单文件 `~/.xiaoqiao/agent.db`，`journal_mode=WAL`，`foreign_keys=ON`。

```sql
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);

CREATE TABLE bots (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  slug          TEXT UNIQUE NOT NULL,
  emoji         TEXT NOT NULL DEFAULT '🤖',
  persona_md    TEXT NOT NULL DEFAULT '',
  model         TEXT NOT NULL DEFAULT '',      -- 空 = 全局 primaryModel
  tools_json    TEXT NOT NULL DEFAULT '[]',    -- 空数组 = 默认工具集
  workspace     TEXT NOT NULL DEFAULT '',      -- 空 = 进程 cwd
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE groups (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  default_bot_id  TEXT REFERENCES bots(id) ON DELETE SET NULL,
  settings_json   TEXT NOT NULL DEFAULT '{}',  -- {autoReply, maxHops, maxBotsPerTurn}
  archived        INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE group_members (
  group_id    TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  member_type TEXT NOT NULL CHECK (member_type IN ('user','bot')),
  member_id   TEXT NOT NULL,                   -- user: 'owner'；bot: bots.id
  joined_at   TEXT NOT NULL,
  PRIMARY KEY (group_id, member_type, member_id)
);

CREATE TABLE channels (
  id            TEXT PRIMARY KEY,
  bot_id        TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,                 -- web | telegram
  config_json   TEXT NOT NULL DEFAULT '{}',
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL
);

-- 外部会话 → 内部 group/session 的映射
CREATE TABLE channel_threads (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  channel_id         TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  external_thread_id TEXT NOT NULL,            -- telegram chat_id / web tab id
  group_id           TEXT REFERENCES groups(id) ON DELETE SET NULL,
  session_id         TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  created_at         TEXT NOT NULL,
  UNIQUE (channel_id, external_thread_id)
);

CREATE TABLE sessions (
  id                TEXT PRIMARY KEY,
  bot_id            TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  group_id          TEXT REFERENCES groups(id) ON DELETE CASCADE,  -- NULL = 私聊
  external_user_id  TEXT NOT NULL DEFAULT 'owner',
  title             TEXT NOT NULL DEFAULT '',
  model             TEXT NOT NULL DEFAULT '',
  workspace         TEXT NOT NULL DEFAULT '',
  status            TEXT NOT NULL DEFAULT 'idle',
  last_seen_seq     INTEGER NOT NULL DEFAULT 0, -- 群聊水位线：已拼进上下文的最大 group_messages.seq
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  UNIQUE (bot_id, group_id)                    -- 每个 Bot 在每个群里一份会话
);
CREATE INDEX idx_sessions_bot ON sessions(bot_id, updated_at DESC);

CREATE TABLE messages (              -- 私聊投影（UI 历史）；权威状态在 framework_session 快照
  session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  role          TEXT NOT NULL,
  payload_json  TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  PRIMARY KEY (session_id, seq)
);

-- 群聊消息是共享事实源：作者、@、回复关系
CREATE TABLE group_messages (
  id            TEXT PRIMARY KEY,
  group_id      TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  author_type   TEXT NOT NULL CHECK (author_type IN ('user','bot','system')),
  author_id     TEXT NOT NULL,                 -- 'owner' / bots.id
  content_json  TEXT NOT NULL,                 -- 文本/结构化内容
  mentions_json TEXT NOT NULL DEFAULT '[]',    -- ["bot_coder","all"]
  reply_to      TEXT,                          -- 被回复的 message id
  run_id        TEXT,                          -- 由哪个 run 产生
  created_at    TEXT NOT NULL,
  UNIQUE (group_id, seq)
);
CREATE INDEX idx_group_messages ON group_messages(group_id, created_at);

CREATE TABLE runs (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  session_id         TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  group_id           TEXT REFERENCES groups(id) ON DELETE SET NULL,
  trigger            TEXT NOT NULL,            -- web | group | telegram | routine | api
  reply_to_message   TEXT,
  parent_run_id      TEXT,                     -- 上一跳（Bot 被 @ 触发）
  hop                INTEGER NOT NULL DEFAULT 0,
  status             TEXT NOT NULL,            -- queued|running|waiting_approval|done|failed|cancelled
  error              TEXT,
  started_at         TEXT,
  ended_at           TEXT,
  created_at         TEXT NOT NULL
);
CREATE INDEX idx_runs_bot ON runs(bot_id, created_at DESC);
CREATE INDEX idx_runs_group ON runs(group_id, created_at DESC);
CREATE INDEX idx_runs_status ON runs(status);

CREATE TABLE routines (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  name               TEXT NOT NULL,
  schedule_json      TEXT NOT NULL,            -- {"kind":"daily","at":"09:00","tz":"Asia/Shanghai"}
  prompt             TEXT NOT NULL,
  target_group_id    TEXT REFERENCES groups(id) ON DELETE SET NULL,
  target_channel_id  TEXT REFERENCES channels(id) ON DELETE SET NULL,
  enabled            INTEGER NOT NULL DEFAULT 1,
  next_run_at        TEXT,
  last_run_at        TEXT,
  created_at         TEXT NOT NULL
);
CREATE INDEX idx_routines_due ON routines(enabled, next_run_at);

CREATE TABLE routine_fires (       -- 同一 routine 的同一计划时刻只跑一次
  routine_id    TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
  scheduled_at  TEXT NOT NULL,
  run_id        TEXT NOT NULL,
  PRIMARY KEY (routine_id, scheduled_at)
);

CREATE TABLE pending_approvals (
  id          TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  call_id     TEXT NOT NULL,
  bot_id      TEXT NOT NULL,
  group_id    TEXT,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,
  channel_id  TEXT,
  status      TEXT NOT NULL DEFAULT 'pending', -- pending|approved|denied|expired
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT                            -- 仅允许 'owner'（人类）
);
CREATE INDEX idx_approvals_pending ON pending_approvals(status, expires_at);

CREATE TABLE memory_facts (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  user_id     TEXT NOT NULL DEFAULT 'owner',
  key         TEXT NOT NULL,
  value       TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'user',    -- user | agent | summary
  confidence  REAL NOT NULL DEFAULT 1.0,
  updated_at  TEXT NOT NULL,
  UNIQUE (bot_id, user_id, key)
);

CREATE TABLE memory_notes (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  user_id     TEXT NOT NULL DEFAULT 'owner',
  session_id  TEXT,
  text        TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE VIRTUAL TABLE memory_notes_fts USING fts5(text, content='memory_notes', content_rowid='rowid');

CREATE TABLE artifacts (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  run_id      TEXT REFERENCES runs(id) ON DELETE SET NULL,
  path        TEXT NOT NULL,
  mime        TEXT,
  size        INTEGER,
  created_at  TEXT NOT NULL
);

CREATE TABLE usage_events (
  id            TEXT PRIMARY KEY,
  run_id        TEXT REFERENCES runs(id) ON DELETE SET NULL,
  bot_id        TEXT NOT NULL,
  model         TEXT NOT NULL,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd      REAL NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);
```

**说明**

- `messages` 是私聊投影，**不是权威**；群聊的共享事实源是 `group_messages`。`framework_session` 快照仍是每个 Bot 的模型状态权威。
- `sessions` 上的 `UNIQUE (bot_id, group_id)` 保证「每个 Bot 在每个群里只有一份上下文」；私聊 `group_id IS NULL` 时用部分索引或应用层约束（SQLite 对 NULL 不参与唯一）。
- 群内 @ 用 slug（`@coder`），展示名可改、slug 稳定；`mentions_json` 存解析后的 bot id，避免前端文本被篡改。
- `group_messages` 与各 Bot 的 session 之间用 **水位线**（`sessions.last_seen_seq`）同步：每次 run 只把新消息拼进上下文。

---

## 5. 后端模块与文件级改动

| 文件 | 动作 | 职责 |
|---|---|---|
| `python/src/xiaoqiao/store.py` | 新增 | SQLite 连接、DDL、事务、`schema_migrations`、迁移执行器 |
| `python/src/xiaoqiao/bots.py` | 新增 | Bot CRUD、slug 生成、默认 Bot 引导、工具白名单解析 |
| `python/src/xiaoqiao/groups.py` | 新增 | Group CRUD、成员增删、默认 Bot、群设置（autoReply/maxHops/maxBotsPerTurn） |
| `python/src/xiaoqiao/router.py` | 新增 | `GroupRouter`：解析 @、选收件人、跳数/冷却/预算校验、派发 Run |
| `python/src/xiaoqiao/runtime/manager.py` | 新增 | `RunManager`：submit/cancel/subscribe、每 session FIFO、run 状态机 |
| `python/src/xiaoqiao/runtime/events.py` | 新增 | EventBus、事件 envelope、序号、按 `replyTo` 排序 |
| `python/src/xiaoqiao/runtime/sessions.py` | 新增 | SessionStore：bot×group 绑定、水位线、投影写入、framework 快照关联 |
| `python/src/xiaoqiao/runtime/approvals.py` | 新增 | ApprovalBroker：落库、TTL 扫描、resolve（仅人类）、恢复 |
| `python/src/xiaoqiao/scheduler.py` | 新增 | 20s tick、`next_run_at`、`routine_fires` 去重、启动补偿 |
| `python/src/xiaoqiao/channels/base.py` | 新增 | `ChannelAdapter` 协议、`InboundMessage`、`OutboundMessage` |
| `python/src/xiaoqiao/channels/telegram.py` | 新增 | 长轮询、发送文本/文件、inline keyboard 审批、群映射 |
| `python/src/xiaoqiao/channels/web.py` | 新增 | 把 WS 连接包装成 adapter（收 prompt、发事件） |
| `python/src/xiaoqiao/memory/store.py` | 新增 | facts CRUD、摘要写入、FTS5 检索、注入裁剪 |
| `python/src/xiaoqiao/artifacts.py` | 新增 | run 结束扫描 `bot.workspace` 新增文件、索引、MIME |
| `python/src/xiaoqiao/executor.py` | 新增 | `Executor` 协议；`LocalExecutor` 复用现有 shell 逻辑 |
| `python/src/xiaoqiao/prompt.py` | 新增 | `build_prompt(bot, group_ctx, memory, skills, mcp)`；群聊时注入参与者与最近消息 |
| `python/src/xiaoqiao/llm/maf_adapter.py` | 新增 | 收口 `agent_framework._*` 私有 import |
| `system_prompt.py` | 改 | `_DEFAULT_INSTRUCTIONS` 拆为 `BASE_CONTRACT`；Coder 文案移到 `presets/coder.md` |
| `session.py` | 改 | 加 `bot_id/group_id`；主存储切 DB，JSONL 作为导出/导入 |
| `automation.py` | 改 | JSON CRUD → 表；执行逻辑交给 scheduler |
| `gateway/ws_server.py` | 改 | 瘦身为协议层：解析请求 → runtime 调用 → 订阅事件；删除 `_session`、`_pending_approvals`、`_handle_prompt` 执行体 |
| `main.py` | 改 | 启动 store → runtime → scheduler → channels；`--legacy-gateway` 保留一版回退 |
| `turn_runner.py` | 改/合并 | runtime 构造与缓存迁入 RunManager |
| `agent_runtime.py` | 小改 | 接受 `run_id`，事件带 `runId`；审批交给 broker 回调 |
| `tools/coding_tools.py` | 改 | 工具工厂接受 `(workspace, allowed_tools)`；`_run_command` 走 Executor |

---

## 6. 协议 v2（WebSocket JSON-RPC）

### 6.1 请求

兼容现有方法（`prompt / cancel / listSessions / createSession / loadSession / deleteSession / updateSession / getSettings / updateSettings / approval_response`），新增：

| 方法 | 参数 | 返回 |
|---|---|---|
| `bots.list` | — | `Bot[]` |
| `bots.create` | `{name, emoji?, persona?, model?, workspace?}` | `Bot` |
| `bots.update` | `{botId, ...patch}` | `Bot` |
| `bots.delete` | `{botId}` | `{ok}`（禁止删除最后一个 bot；群内成员一并移除） |
| `bots.previewPrompt` | `{botId, groupId?}` | `{prompt}` |
| `groups.list` | — | `Group[]`（含成员与默认 Bot） |
| `groups.create` | `{name, botIds[], defaultBotId?}` | `Group` |
| `groups.update` | `{groupId, name?, defaultBotId?, settings?}` | `Group` |
| `groups.addMember` | `{groupId, botId}` | `Group` |
| `groups.removeMember` | `{groupId, botId}` | `Group` |
| `groups.delete` | `{groupId}` | `{ok}`（会话与消息级联） |
| `messages.list` | `{groupId, before?, limit?}` | `GroupMessage[]` |
| `runs.list` | `{botId?, groupId?, status?, limit?}` | `Run[]` |
| `runs.get` | `{runId}` | `Run` |
| `runs.cancel` | `{runId}` | `{ok}` |
| `approvals.list` | `{status?}` | `Approval[]` |
| `approvals.resolve` | `{approvalId, approved}` | `{ok}`（仅人类） |
| `routines.list` | `{botId?}` | `Routine[]` |
| `routines.upsert` | `{routineId?, botId, name, schedule, prompt, targetGroupId?}` | `Routine` |
| `routines.toggle` | `{routineId, enabled}` | `Routine` |
| `channels.list` | `{botId}` | `Channel[]` |
| `channels.connect` | `{botId, kind, config}` | `Channel` |
| `channels.test` | `{channelId}` | `{ok, error?}` |
| `memory.list` | `{botId}` | `Fact[]` |
| `memory.upsert` | `{botId, key, value}` | `Fact` |
| `memory.delete` | `{botId, key}` | `{ok}` |
| `artifacts.list` | `{botId?, runId?}` | `Artifact[]` |

`prompt` 参数扩展：

```json
{"method":"prompt","params":{"text":"@coder 整理一下","groupId":"g_1","mentions":["bot_coder"],"sessionId":"s_1"}}
```

- 带 `groupId` → 群聊消息：服务端写 `group_messages`，由 `GroupRouter` 派发。
- 不带 `groupId` 但带 `botId` → 私聊，直接提交 run。
- 都不带 → 默认 Bot（兼容旧客户端）。

### 6.2 事件

统一 envelope，**所有事件**都带归属字段：

```json
{"type":"text_delta","runId":"run_x","botId":"bot_y","sessionId":"s","groupId":"g_1","replyTo":"msg_9","seq":12,"delta":"…"}
```

新增事件：

- `group_message_created{message}` — 群消息落库后广播（含用户消息与 Bot 回复）
- `bot_typing{botId, groupId}` — 供群内多 Bot 的「正在输入」
- `run_started` / `run_finished{status,error?}`
- `approval_requested{approvalId,tool,args,expiresAt}` / `approval_resolved{approvalId,status}`
- `artifact_created{artifact}`

兼容策略：旧客户端忽略未知字段；`text_delta`/`thinking_delta`/`tool_*`/`turn_end`/`done` 保持原有字段不变。

### 6.3 错误模型

```json
{"type":"rpc_response","id":"rpc_1","error":{"code":"group_not_found","message":"…","retryable":false}}
```

错误码：`bot_not_found`、`group_not_found`、`session_not_found`、`run_conflict`、`hop_limit_exceeded`、`approval_expired`、`channel_auth_failed`、`internal`。

---

## 7. 前端：信息架构与实现

### 7.1 IA

```
┌──────┬────────────────┬──────────────────────────┬──────────────┐
│ Bots │ 群聊 / 私聊      │ 对话（max 760px 居中）     │ 上下文面板    │
│ 64px │ 264px          │  消息（作者头像 + @）      │ 460px        │
│      │  · 群：Coder 组  │  多 Bot 输入中 / 审批卡片   │ 参与者·人格·  │
│      │  · 私聊：盯盘    │  Composer（32px 圆角）     │ 记忆·定时·产物│
└──────┴────────────────┴──────────────────────────┴──────────────┘
侧栏底部：Routines · Skills · Channels · Memory · Approvals · Settings
```

尺寸依据 [design.md](design.md)：`--p-rail-w` 64 / `--p-sidebar-w` 264 / `--p-content-max` 760 / `panel-default-w` 460；群聊专属规范见 design.md §13。

- 侧栏分两段：**群聊**（人 + 多 Bot）与**私聊**（单个 Bot）；新建按钮可选「新建群聊 / 新建私聊」。
- 群聊头部展示参与者头像，可点开群设置：默认应答 Bot、是否自动应答、跳数上限。
- 输入框 `@` 触发 Bot 选择器（按 slug/名称过滤），支持 `@all`。
- 每个 Bot 的回复带自己的头像与名字；多个 Bot 同时工作时分别显示「正在输入」。
- 审批卡片只对人类显示可点按钮；Bot 消息里的审批请求标注「等待你确认」。

### 7.2 路由

| 路由 | 组件 | 说明 |
|---|---|---|
| `/` | `BotHomeView` | Bot 网格 + 最近群聊 |
| `/g/:groupId` | `GroupView` | 群聊主界面 |
| `/b/:botId` | `BotWorkspaceView` | 私聊 |
| `/b/:botId/c/:sessionId` | `ChatSessionView`（现有） | 私聊对话 |
| `/approvals` | `ApprovalsView` | 全局审批收件箱（跨 Bot / 群） |
| `/routines` | `RoutinesView` | 按 Bot 分组的定时任务 |
| `/toolbox/*`、`/settings/*` | 现有 | 加 `?bot=` 作用域 |

### 7.3 组件与文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `components/bots/BotRail.vue` | 新增 | 头像列、运行脉冲、`+` 新建、hover 名称 |
| `components/bots/BotAvatar.vue` | 新增 | emoji/图片头像 + 状态点 |
| `components/bots/BotEditorModal.vue` | 新增 | 名称、emoji、persona、模型、工作目录 |
| `components/groups/GroupList.vue` | 新增 | 群聊 + 私聊分区列表 |
| `components/groups/GroupHeader.vue` | 新增 | 参与者头像、群设置入口 |
| `components/groups/GroupSettingsModal.vue` | 新增 | 默认 Bot、自动应答、跳数上限、成员增删 |
| `components/groups/MentionPicker.vue` | 新增 | `@` 触发、键盘导航、显示 Bot 头像 |
| `components/groups/TypingIndicator.vue` | 新增 | 多 Bot 各自的「正在输入」 |
| `components/chat/GroupMessageItem.vue` | 新增 | 作者头像 + 名字 + 内容 + @ 高亮 |
| `components/chat/ArtifactTray.vue` | 新增 | 产物列表、预览、下载 |
| `components/chat/ApprovalInline.vue` | 新增 | 仅人类可点，TTL 倒计时 |
| `views/GroupView.vue` | 新增 | 群聊主界面（复用 MessageList 的虚拟滚动） |
| `views/BotHomeView.vue` | 新增 | Bot 网格 + 最近群 |
| `views/ApprovalsView.vue` | 新增 | 收件箱：pending / 历史 / 过期 |
| `views/routines/RoutinesView.vue` | 新增 | 定时任务列表 + 编辑器 |
| `stores/bots.ts` | 新增 | 列表、activeBotId、CRUD |
| `stores/groups.ts` | 新增 | 群列表、成员、默认 Bot、消息分页 |
| `stores/runs.ts` | 新增 | 活跃 run、状态订阅、取消 |
| `stores/approvals.ts` | 新增 | 收件箱、resolve、TTL 倒计时 |
| `stores/artifacts.ts` | 新增 | 按 run/bot 拉取 |
| `stores/sessions.ts` | 改 | `SessionInfo.botId/groupId`；按群/Bot 过滤 |
| `stores/chat.ts` | 改 | 群内事件按 `groupId + replyTo` 归位 |
| `services/gateway.ts` | 改 | 类型化调用、错误码映射、重连后重订阅 |
| `types/bot.ts`、`types/group.ts`、`types/run.ts`、`types/approval.ts` | 新增 | 与协议 v2 对齐 |
| `web/src/styles/tokens.css` | 改 | 补齐 design.md §13.9 的 `--p-*` 群聊私有 token；**不新增颜色** |
| `web/src/styles/` 旧变量清理 | 改 | 按 §7.5 清单替换 `--border` / `--bg-card` / `#d9896d` 等 |

### 7.4 状态与交互规范

| 场景 | 行为 |
|---|---|
| 群内发消息 | 乐观插入用户消息（带 mentions）→ 服务端回 `group_message_created` 校准 → 每个被 @ 的 Bot 显示输入中 |
| 多个 Bot 同时回 | 按 `replyTo` 分桶串行渲染；先到的先显示，但保持「回复同一条消息」的视觉分组 |
| 未 @ 任何 Bot | 使用群默认 Bot；若未设置默认 Bot，提示「选一个默认应答 Bot」 |
| 触达跳数上限 | 群内插入系统消息（12px `--color-text-faint`，居中）「已达到 3 跳上限，继续对话请手动 @」 |
| 审批 | 只有人类可见按钮；Bot 消息里的审批标注「等待你确认」；过期自动置灰 |
| 切换群/Bot | 切列表不打断运行；rail 与群列表显示运行脉冲 |
| 键盘操作 | @ 选择器 ↑↓/Enter/Esc；消息跳转可 Tab；审批按钮可 Enter；焦点环用 `--p-focus-ring-strong` |
| 减少动效 | `prefers-reduced-motion: reduce` 下关闭输入中动画与消息进入位移，只保留透明度切换 |
| 空状态 | 无群：引导「建一个群，把几个 Bot 拉进来」；无 Bot：先建 Bot |
| 加载/错误 | 骨架屏；错误码直出 + 重试 |

**设计约束**：一切以 [design.md](design.md) 为准。颜色/间距/字号只用 `tokens.css` 的 token；禁止写死色值；暗色只覆盖语义 token；状态色必须「底色 + 边框 + 文字」成套；新增尺寸只允许 `--p-*` 组件私有。

### 7.5 规范对齐与既有偏差清理

| 界面元素 | design.md 依据 | 必须复用的 token |
|---|---|---|
| Bot 轨道 / 头像 | §8.2 IconButton、§13.1 | `--p-rail-w`、`--color-hover`、`--color-selected` |
| 群聊/私聊列表 | §8.8 Menu 行高、§3.1 表面 | `--color-sidebar-bg`、`--color-hover`、`--color-selected` |
| 消息与作者行 | §13.2 | `--color-user-bubble-bg`、`--p-avatar-sm`、`--text-sm` / `--text-xs` |
| @ 提及 | §13.3 | `--color-accent-soft`、`--color-accent`、`--radius-xs` |
| @ 选择器 | §8.8 Menu、§13.4 | `--shadow-menu`、`--color-menu-bg`、`--radius-lg` |
| 多 Bot 输入中 | §6.2、§13.5 | `--color-text-faint`、`--duration-flash` |
| 群设置对话框 | §8.9 Dialog（md 440） | `--shadow-xl`、`--radius-xl`、`--color-surface-raised` |
| 群内审批卡 | §8.6 ActionCard、§13.7 | `--color-warning-*` / `--color-danger-*` 成套 |
| 跳数上限提示 | §8.5 Banner / §13.2 系统消息 | `--color-surface`、`--color-line`、`--text-xs` |
| Composer | §8.14 | `--radius-composer`、`--color-send-bg`、`--shadow-input` |
| 空状态 / Toast | §8.10、§10 | `--color-surface-raised`、`--shadow-sm` |

**本次必须顺手清掉的偏差**（都在现有 `web/src/` 里）：

1. 旧变量 `--border` / `--bg-card` / `--bg-page` / `--text-muted` 等仍被大量组件引用 → 迁到 `--color-line` / `--color-surface-raised` / `--color-bg` / `--color-text-muted`（design.md §0 明确旧变量仅过渡）。
2. 硬编码色 `#d9896d`（`SettingsPersonalityView.vue`、`EventListenersView.vue` 等）→ 状态/强调一律换 token。
3. 侧栏 `w-64`（256px）与规范 `--p-sidebar-w`（264px）不一致 → 改 token。
4. 组件里混用 `rounded-xl` / 自定义圆角 → 统一到 §5.2 的 `--radius-*`。
5. 焦点态缺失或 `outline: none` 无补偿 → 统一 `:focus-visible` + `--p-focus-ring`。
6. `opacity` 弱化文字 → 改 `--color-text-muted` / `--color-text-faint`。

---

## 8. 关键流程

### 8.1 群聊消息路由

```
用户发送 "@盯盘 查行情"（mentions=["bot_watch"]）
 → gateway 校验 mentions ⊆ group_members(bot)
 → 写 group_messages(author=owner, mentions=[…])
 → GroupRouter.dispatch：
      recipients = mentions（空则 default_bot_id；@all 则全部成员）
      recipients 截断到 maxBotsPerTurn
      for bot in recipients: RunManager.submit(trigger="group", reply_to=m, hop=0)
 → 各 Bot 独立组装上下文（系统提示 + 参与者 + 最近 N 条群消息 + 自己的历史）
 → 回复落 group_messages(author=bot)，带 reply_to=用户消息
 → 若回复里 @ 了其他 Bot 且 hop < maxHops：派发下一跳（hop+1，parent_run_id 记录）
 → hop 达上限：写 system 消息提示，停止派发
```

**防环规则（runtime 强制）**

1. `hop ≤ maxHops`（默认 3）。
2. 同一用户消息触发的 Bot 数 ≤ `maxBotsPerTurn`（默认 3）。
3. 同一 Bot 在无新用户消息的情况下不得连续被触发两次。
4. 同一 Bot 两次 run 之间至少 2s 冷却（防抖）。
5. 任何一条命中即停并落一条 `system` 群消息说明原因。

### 8.2 群上下文组装

```
for bot in recipients:
    watermark = sessions(bot, group).last_seen_seq
    new_messages = group_messages(group, seq > watermark)
    prompt = BASE_CONTRACT + bot.persona + participant_roster
           + render(new_messages)      # 每条前缀 [作者名]，自己的历史用 assistant 角色
           + memory(bot) + skills + mcp
    run(bot, prompt, reply_to=last_user_message)
    sessions.last_seen_seq = max(seq)
```

- 只把**新消息**拼进上下文，避免每轮重放全量群聊。
- 渲染时对超长消息截断（单条 ≤ 4k 字符），总预算按模型上下文动态计算。
- 其他 Bot 的消息以 `user` 角色注入并带作者前缀；自己发过的以 `assistant` 角色注入。

### 8.3 私聊 Run

```
WS prompt{botId, text, sessionId?}
 → runtime.submit → run=queued → ack runId
 → 组装 prompt（base+persona+memory+skills）
 → 事件经 EventBus 广播（runId/botId/sessionId）
 → 结束：写 messages 投影、framework 快照、usage、artifacts → run=done
```

### 8.4 审批

```
工具需审批 → run=waiting_approval
 → pending_approvals 落库（TTL 30min，记录 group_id）
 → 广播 approval_requested
 → Web 群内卡片 / Telegram inline keyboard（仅人类身份可点）
 → resolve：校验身份、状态、TTL → 恢复 run
 → 超时：定时扫描置 expired，run=failed(approval_expired)
```

### 8.5 Routine 触发

```
scheduler tick(20s) → 查 enabled 且 next_run_at<=now
 → 事务写 routine_fires（PK 去重）→ runtime.submit(trigger="routine")
 → 结果投递到 target_group / target_channel；审批走 broker
```

---

## 9. 迁移方案

| 步骤 | 内容 | 回滚 |
|---|---|---|
| M1 | 建库与 DDL（`schema_migrations` v2） | 删 `agent.db` 即可，旧数据未动 |
| M2 | 导入旧会话：读 `sessions.json` + `*.jsonl`，建 `default` bot，私聊会话（`group_id=NULL`），幂等 upsert | 保留原文件只读；重跑幂等 |
| M3 | 导入旧自动化：`scheduled_tasks.json` / `event_listeners.json` → `routines` | 原文件保留 |
| M4 | 切换读写路径：`session.py` 读写 DB，JSONL 仅导出 | `--legacy-gateway` 开关回退一版 |
| M5 | 前端切 group/bot 路由 | 旧路由保留重定向到默认 Bot 的私聊 |

迁移脚本：`scripts/migrate_v1.py`，带 `--dry-run` 与计数输出；迁移前后各跑一次 `pytest`。

---

## 10. WBS（工作分解）

> 估算按 1 名熟悉本仓库的开发者，单位：人日；含自测，不含评审等待。

| WP | 内容 | 依赖 | 产出（DoD） | 估算 |
|---|---|---|---|---|
| WP0 | 协议 v2 定义 + TS 类型 + 错误码 | — | `docs/protocol.md` 更新；类型编译通过 | 0.5 |
| WP1 | `store.py` + DDL + 迁移脚本 | WP0 | DDL 幂等、外键级联、迁移可重跑 | 1.0 |
| WP2 | `bots.py` + `prompt.py`（persona 注入） | WP1 | 两 Bot prompt 不同；`test_bots.py` | 1.5 |
| WP3 | `runtime/manager.py` + EventBus + run 状态机 | WP1/2 | submit→事件→done；同 session 串行；cancel | 2.0 |
| WP4 | Gateway 瘦身 + 新方法 | WP3 | 旧方法兼容；契约测试 | 1.5 |
| WP5 | ApprovalBroker（落库/TTL/跨入口/仅人类） | WP3/4 | 重启可恢复；Bot 身份 resolve 被拒 | 1.5 |
| WP6 | 前端 IA：BotRail + Bot 首页 + 编辑页 + 私聊 + 旧变量清理 | WP2/4 | 两 Bot 会话隔离；刷新保持；`--border`/`--bg-card`/`#d9896d` 清零 | 2.5 |
| WP7 | `groups.py` + `router.py`：@ 解析、收件人、防环 | WP3/5 | 路由表单测；跳数/冷却/预算命中即停 | 2.0 |
| WP8 | 群上下文组装（水位线、作者前缀、裁剪） | WP2/7 | 各 Bot 上下文互不污染；长群不爆 token | 1.5 |
| WP9 | 前端群聊：GroupList/GroupView/@ 选择器/多 Bot 输入中（按 design.md §13） | WP6/7 | 群内 @ 两个 Bot 均能回；回复按 replyTo 分组；键盘与 reduced-motion 通过 | 3.0 |
| WP10 | Scheduler + routines（先投递到群） | WP3/5 | 到点一次、去重、补偿；9:00 进群 | 1.5 |
| WP11 | Telegram adapter + 群映射 | WP7/10 | 文本/文件/按钮；群内 @ 多 Bot | 2.5 |
| WP12 | Memory（facts/摘要/FTS，按 bot×user） | WP2/3 | 注入截断、检索命中、群摘要分别沉淀 | 2.0 |
| WP13 | Artifacts（扫描/索引/预览） | WP3 | run 后产物可见 | 1.0 |
| WP14 | 前端 runs/approvals/artifacts | WP5/13 | 后台 run 可见；收件箱可批；产物可预览 | 2.0 |
| WP15 | 前端 routines/channels/memory 页 | WP10/11/12 | 建 routine→接渠道→看记忆三步可完成 | 2.0 |
| WP16 | 加固：预算、限流、备份、CI | 全部 | 每 Bot/群预算；CI 三件套 | 2.0 |

**合计约 31 人日**（含按 design.md 清理旧变量与补齐群聊界面规范）。

**关键路径**：WP0 → WP1 → WP2/WP3 → WP4 → WP6（M1）；WP7 → WP8 → WP9（M2）；WP10/11（M3）；WP12–15（M4）。

---

## 11. 里程碑

| 里程碑 | 范围 | 工期 | 验收 |
|---|---|---|---|
| M0 契约冻结 | WP0 | 0.5 天 | 前后端对类型、错误码无异议 |
| M1 多 Bot 闭环 | WP1–WP6 | 约 1.5–2 周 | 两个 Bot 人格/模型不同、会话隔离、关网页 run 继续、刷新可恢复 |
| M2 群聊 | WP7–WP9、WP10 | 约 2 周 | 建群拉 3 个 Bot；@ 指定应答；Bot 交接 ≤3 跳；9:00 日报进群；Bot 审批被拒 |
| M3 渠道 | WP11 | 约 1 周 | Telegram 群多 Bot 互 @；收文件；按钮审批 |
| M4 记忆与交付 | WP12–WP15 | 约 1.5 周 | 跨会话/跨群记忆正确；产物可预览可发送 |
| M5 加固 | WP16 | 约 2–3 天 | CI 绿；预算与限流生效；备份可恢复 |

> 与 product.md 阶段对应：M1≈P0（地基）、M2≈P1（群聊+主动性）、M3≈P2（渠道）、M4≈P3（记忆+交付）、M5≈P4（加固）。

---

## 12. 测试策略

| 层 | 用例 | 工具 |
|---|---|---|
| 存储 | DDL 幂等、迁移重跑、级联删除、`UNIQUE(bot,group)` | pytest |
| Bot/Prompt | 两 Bot prompt 差异、空 persona 回退、工具白名单 | pytest |
| 路由 | 路由表驱动：`@a`、`@a @b`、`@all`、无 mention、非成员 mention、大小写/slug 别名 | pytest |
| 防环 | 跳数上限、每轮 Bot 数上限、同 Bot 连续触发、冷却窗口 | pytest（可控时钟） |
| 群上下文 | 水位线推进、作者前缀正确、超长截断、自己的消息用 assistant 角色 | pytest |
| Runtime | 串行队列、cancel、审批暂停/恢复、崩溃恢复 | pytest + asyncio |
| 审批 | 仅人类可批；Bot 身份 resolve 返回 `forbidden`；TTL 过期 | pytest |
| Scheduler | 到点一次、去重、disabled、补偿 | pytest + 可控时钟 |
| 渠道 | 群映射、@ 解析、按钮回调、发送重试 | pytest + 假 HTTP |
| 协议 | 每个 RPC 的成功/错误分支 | pytest + 假 WS |
| 前端 | groups/chat store、@ 选择器、按 replyTo 分组、空状态 | vitest + @vue/test-utils |
| E2E | 建群 → @ 两个 Bot → 交接 → 审批 → 产出 | `_FakeClient` 驱动的脚本 |

CI（新增 `.github/workflows/ci.yml`）：`ruff check` + `pyright` + `pytest`；`pnpm type-check` + `pnpm test:unit` + `pnpm build`。

---

## 13. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| Bot 互 @ 死循环 | 无限对话、账单爆炸 | 跳数/轮次/冷却/同 Bot 连续触发四重限制，命中即停并提示 |
| 群上下文膨胀 | 每个 Bot 重放全量群消息 | 水位线增量 + token 预算裁剪 + 超长单条截断 |
| 多 Bot 回复乱序 | 可读性差 | 按 `replyTo` 分桶、群级发送队列串行化 |
| AgentSession 权威性被破坏 | 工具配对断裂 | 每 Bot 独立 Session；快照与投影同事务写；契约测试 |
| 审批跨渠道时序 | 重复 resolve / 超时竞态 | DB 状态机 CAS + TTL 扫描 + 仅人类身份 |
| 单进程阻塞 | 长任务拖慢所有 Bot | 工具在子进程；LLM 调用并发；每 run 超时 |
| 提示注入（渠道） | 危险工具被诱导 | untrusted 标记 + 白名单 + 强制审批 |
| 迁移数据丢失 | 用户历史会话 | 原文件只读保留、dry-run、幂等 |
| 成本失控 | 一次消息触发多个 Bot | 每 Bot/群预算；群聊默认只 @ 一个；跳数上限同时是成本上限 |
| 前后端契约漂移 | UI 反复返工 | WP0 冻结类型；协议测试 |

---

## 14. 评审检查清单

- [ ] 每个 WP 都有可执行的 DoD 与测试文件
- [ ] 旧客户端（只发 `prompt` 不带 `botId/groupId`）仍可用
- [ ] 迁移脚本可 dry-run、可重跑、失败不破坏旧数据
- [ ] 群路由表覆盖「非成员 mention」「@all」「无 mention」三种边界
- [ ] 防环四种限制都有测试，且失败时群内有可读提示
- [ ] 审批在「无 Web 连接」场景下有入口，且 Bot 无法代批
- [ ] 删除 Bot/群时成员与会话的级联行为有二次确认与说明
- [ ] 所有新组件只使用 `tokens.css` 变量
- [ ] CI 覆盖后端与前端

---

## 附：与 v1 的差异

| 项 | v1（旧 pivot-plan） | v2 |
|---|---|---|
| 基线 | `22e225e` | `f44ff33` |
| 文件引用 | `loop.py`、`workflow_loop.py` | `agent_runtime.py`、`turn_runner.py`、`framework_session.py` |
| 协作模型 | 无 | 新增 Group / group_members / group_messages / GroupRouter |
| 上下文隔离 | 未讨论 | 每 Bot 每群独立 Session + 水位线增量 |
| Run 模型 | 只有 `runs` 表 | 状态机、串行队列、hop/parent_run_id、事件 envelope |
| 审批 | 描述流程 | 落库字段、TTL、仅人类可批 |
| 前端 | 只有文件列表 | IA、群聊/私聊分区、@ 选择器、多 Bot 输入中、状态规范 |
| 估算 | 按周粗估 | 按 WP 人日 + 关键路径（约 30 人日） |
