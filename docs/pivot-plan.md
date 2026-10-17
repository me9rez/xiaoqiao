# 改造落地方案：多 Bot 常驻运行时

> 配套文档：[product.md](product.md)（产品方向与路线图）。
> 本文只讲工程：目标架构、数据模型、接口、文件级改动、迁移与测试。
> 基线：master `22e225e`。

---

## 1. 目标架构

现状是「Gateway 即应用」：一次对话必须挂在一条 WebSocket 上，routine 和外部渠道没有入口。
目标是把执行下沉到常驻 Runtime，Gateway 变成它的一个客户端。

```
                  ┌──────────── 渠道层 channels/ ────────────┐
                  │ telegram.py    x_dm.py(后)   web.py(WS)  │
                  └──────────────────┬───────────────────────┘
                                     │ InboundMessage（归一化）
                                     ▼
┌────────────────────── Runtime（常驻进程） ──────────────────────┐
│  BotRegistry   SessionStore   RunManager   ApprovalBroker      │
│  Scheduler（20s tick）──► RunManager.submit(source="routine")  │
│  EventBus（所有事件在此汇聚，Gateway/渠道各自订阅）              │
└───────────────┬─────────────────────────────────┬──────────────┘
                │ 一次 run = 一次 MAF Agent 执行   │ 事件
                ▼                                 ▼
        ┌───────────────┐                 ┌───────────────┐
        │ Executor      │                 │ Gateway (WS)  │
        │ local/docker  │                 │ 仅协议转换     │
        └───────┬───────┘                 └───────┬───────┘
                │                                 │
        ┌───────▼───────┐                 ┌───────▼───────┐
        │ 工具 + 沙箱    │                 │ Vue 前端       │
        └───────────────┘                 └───────────────┘
```

**边界原则**

- `runtime/` 不 import `gateway/`；`gateway/` 只依赖 runtime 的公开方法。
- 渠道适配器只做「收/发 + 协议翻译」，不含 agent 逻辑。
- 一次 run 的所有副作用（审批、产物、用量）都落库，进程重启可恢复。

---

## 2. 数据模型

单文件 `~/.xiaoqiao/agent.db`，WAL 模式，`foreign_keys=ON`。
JSONL 保留为导出格式，不再作为主存储。

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE bots (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  slug          TEXT UNIQUE NOT NULL,
  avatar        TEXT DEFAULT '',
  persona_md    TEXT DEFAULT '',            -- SOUL.md 内容，直接拼进 prompt
  model         TEXT DEFAULT '',            -- 空 = 全局默认
  tools_json    TEXT DEFAULT '[]',          -- 工具白名单，空 = 默认集
  workspace     TEXT DEFAULT '',            -- 该 bot 的工作目录
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE channels (
  id            TEXT PRIMARY KEY,
  bot_id        TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,              -- telegram | x_dm | web
  config_json   TEXT NOT NULL DEFAULT '{}', -- token 等，加密后存
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL
);

CREATE TABLE sessions (
  id                TEXT PRIMARY KEY,
  bot_id            TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  channel_id        TEXT REFERENCES channels(id) ON DELETE SET NULL,
  external_user_id  TEXT NOT NULL DEFAULT 'owner',
  title             TEXT DEFAULT '',
  model             TEXT DEFAULT '',
  workspace         TEXT DEFAULT '',
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE INDEX idx_sessions_bot ON sessions(bot_id, updated_at DESC);

CREATE TABLE messages (
  session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  role          TEXT NOT NULL,
  payload_json  TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  PRIMARY KEY (session_id, seq)
);

CREATE TABLE runs (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  session_id  TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  trigger     TEXT NOT NULL,                -- web | telegram | routine | api
  status      TEXT NOT NULL,                -- queued|running|waiting_approval|done|failed|cancelled
  started_at  TEXT,
  ended_at    TEXT,
  error       TEXT
);
CREATE INDEX idx_runs_bot ON runs(bot_id, started_at DESC);

CREATE TABLE routines (
  id                 TEXT PRIMARY KEY,
  bot_id             TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  name               TEXT NOT NULL,
  schedule_json      TEXT NOT NULL,         -- {"kind":"daily","at":"09:00","tz":"Asia/Shanghai"}
  prompt             TEXT NOT NULL,
  target_channel_id  TEXT REFERENCES channels(id) ON DELETE SET NULL,
  enabled            INTEGER NOT NULL DEFAULT 1,
  next_run_at        TEXT,
  last_run_at        TEXT
);
CREATE INDEX idx_routines_due ON routines(enabled, next_run_at);

-- 去重：同一 routine 的同一计划时刻只跑一次
CREATE TABLE routine_fires (
  routine_id   TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
  scheduled_at TEXT NOT NULL,
  run_id       TEXT NOT NULL,
  PRIMARY KEY (routine_id, scheduled_at)
);

CREATE TABLE pending_approvals (
  id          TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  call_id     TEXT NOT NULL,
  bot_id      TEXT NOT NULL,
  tool        TEXT NOT NULL,
  args_json   TEXT NOT NULL,
  channel_id  TEXT,
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending'  -- pending|approved|denied|expired
);

CREATE TABLE memory_facts (
  id          TEXT PRIMARY KEY,
  bot_id      TEXT NOT NULL,
  user_id     TEXT NOT NULL DEFAULT 'owner',
  key         TEXT NOT NULL,
  value       TEXT NOT NULL,
  source      TEXT DEFAULT 'user',          -- user | agent | summary
  confidence  REAL DEFAULT 1.0,
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
  run_id      TEXT,
  path        TEXT NOT NULL,
  mime        TEXT,
  size        INTEGER,
  created_at  TEXT NOT NULL
);
```

**迁移**：`scripts/migrate_jsonl.py`
- 读 `~/.xiaoqiao/sessions/*.jsonl`，建一个 `default` bot，导入 session/messages。
- 旧文件保留只读，不删除；失败可重跑（幂等，按 session_id upsert）。

---

## 3. 关键接口

### 3.1 Runtime

```python
@dataclass(frozen=True)
class RunRequest:
    bot_id: str
    text: str
    source: Literal["web", "telegram", "routine", "api"]
    session_id: str | None = None
    user_id: str = "owner"
    channel: ChannelRef | None = None

class Runtime:
    async def submit(self, req: RunRequest) -> str: ...
    async def resolve_approval(self, approval_id: str, approved: bool) -> None: ...
    async def cancel(self, run_id: str) -> None: ...
    def subscribe(self, cb: Callable[[Event], Awaitable[None]]) -> None: ...
```

- 并发：**同一 session 同时只允许一个 run**，其余排队（`asyncio.Queue` per session）。
- 取消：`cancel` 设置标志位，工具边界检查，不强杀线程。

### 3.2 渠道适配器

```python
class ChannelAdapter(Protocol):
    async def start(self, runtime: Runtime) -> None: ...
    async def send_text(self, chat_id: str, text: str, buttons: list[Button] | None = None) -> None: ...
    async def send_file(self, chat_id: str, path: str, caption: str = "") -> None: ...
```

`InboundMessage` 统一字段：`bot_id / channel / external_chat_id / external_user_id / text / attachments / raw`。

Telegram 先行：长轮询收消息；审批用 inline keyboard（`callback_data = "ap:<approval_id>:1"`）。

### 3.3 Executor

```python
class Executor(Protocol):
    async def exec(self, cmd: str, cwd: str, timeout: float) -> ExecResult: ...
    async def read(self, path: str) -> bytes: ...
    async def write(self, path: str, data: bytes) -> None: ...
```

- `LocalExecutor`：现有 `_run_command` 行为，默认。
- `DockerExecutor`：每 bot 一容器，挂载 `bot.workspace`，默认禁网。
- 只替换 `_run_command` 内部实现，工具签名不变。

### 3.4 Prompt 组装

```python
def build_prompt(bot, user, channel_ctx, skills, mcp) -> str:
    return "\n\n".join(filter(None, [
        BASE_CONTRACT,        # 工具协议 / 审批 / 安全 / 输出规范（共享）
        bot.persona_md,       # SOUL.md
        memory_block(user),   # facts（≤2k 字符）+ top-5 notes
        channel_context(...), # 谁、在哪儿、能否发文件
        skills, mcp,
    ]))
```

现有 `_DEFAULT_INSTRUCTIONS` 抽成 `presets/coder.md`，作为 Coder 模板 bot 的人格。

### 3.5 审批跨渠道

```
工具要求审批 → run 进入 waiting_approval
  → 写 pending_approvals（TTL 30 min）
  → EventBus 广播 ApprovalRequested
  → 渠道层渲染按钮 / Web UI 弹卡片（同一 approval_id）
  → 任一入口 resolve → 恢复 run；超时 → denied(expired)
```

---

## 4. 文件级改动

| 文件 | 动作 | 说明 |
|---|---|---|
| `python/src/xiaoqiao/store.py` | 新增 | SQLite 连接、DDL、事务、迁移 |
| `python/src/xiaoqiao/bots.py` | 新增 | Bot CRUD、默认 bot、工作目录 |
| `python/src/xiaoqiao/runtime.py` | 新增 | RunManager / ApprovalBroker / EventBus / 队列 |
| `python/src/xiaoqiao/scheduler.py` | 新增 | 20s tick、next_run_at、去重、补偿 |
| `python/src/xiaoqiao/channels/base.py` | 新增 | `ChannelAdapter` 协议、`InboundMessage` |
| `python/src/xiaoqiao/channels/telegram.py` | 新增 | 长轮询、发送、审批按钮 |
| `python/src/xiaoqiao/memory/` | 新增 | facts / notes / 摘要 / 检索 |
| `python/src/xiaoqiao/executor.py` | 新增 | Local / Docker 执行器 |
| `python/src/xiaoqiao/llm/maf_adapter.py` | 新增 | 收口 MAF 私有 import |
| `system_prompt.py` | 改 | 拆 BASE_CONTRACT / persona / preset |
| `session.py` | 改 | 加 `bot_id`；逐步迁 SQLite |
| `automation.py` | 改 | JSON CRUD → DB；执行逻辑交给 scheduler |
| `gateway/ws_server.py` | 改 | 瘦身；新增 bot/memory/run/artifact 方法 |
| `main.py` | 改 | 启动 Runtime + Scheduler + Channels |
| `web/src/stores/bots.ts` | 新增 | Bot 状态 |
| `web/src/components/chat/BotSwitcher.vue` | 新增 | 切换器 |
| `web/src/views/settings/SettingsChannelsView.vue` | 重写 | 渠道配置与测试 |
| `web/src/views/settings/SettingsMemoryView.vue` | 重写 | facts 增删改 |
| `web/src/views/settings/SettingsPersonalityView.vue` | 改 | 读写后端 |
| `web/src/views/ApprovalsView.vue` | 新增 | 全局审批收件箱 |

**新增 WS 方法**：`listBots / getBot / createBot / updateBot / deleteBot / listRuns / getRun / listArtifacts / getApproval / resolveApproval / listMemory / upsertMemory / deleteMemory / listChannels / connectChannel / testChannel`。

---

## 5. 实施顺序与验收

### P0（约 1 周）

1. `store.py` + DDL + 迁移脚本
2. `bots.py` + 默认 bot
3. `runtime.py`：submit / cancel / approval / event bus
4. `ws_server.py` 瘦身，全部请求带 `botId`
5. `build_prompt` 接 persona；Coder 模板落 `presets/`
6. 前端 Bot 切换器 + 人格页接后端

**验收**：两个 bot 不同人格/模型，会话隔离；切换后 prompt 变化；关网页进程仍活。

### P1（1–2 周）

1. `scheduler.py` + `routine_fires` 去重 + 启动补偿
2. `channels/telegram.py`
3. 审批落库 + 按钮 + TTL
4. `send_message` 工具（主动发送）

**验收**：9:00 主动发日报；Telegram 可对话/审批/收文件；进程重启后错过的 routine 补跑一次（可配置）。

### P2（约 2 周）

1. `memory/`：facts 注入、摘要、FTS5 检索
2. 产物扫描 + `artifacts` + 预览/发送
3. 注入防护与工具白名单

**验收**：跨会话记得偏好；产物可预览可发送。

### P3（按需）

Playwright 工具、Docker 执行器、登录/配额、Team bots、X DM。

---

## 6. 测试策略

仓库目前无 CI，重构期必须补上（GitHub Actions：`ruff` + `pytest` + `pnpm test:unit`）。

| 层 | 用例 |
|---|---|
| `test_store.py` | DDL 幂等；迁移脚本可重跑；外键级联 |
| `test_runtime.py` | submit→事件→done；审批暂停/恢复；同 session 串行；cancel |
| `test_scheduler.py` | 到点触发一次；`routine_fires` 去重；disabled 跳过；错过的任务补偿 |
| `test_memory.py` | facts 注入与截断；摘要写入；检索命中 |
| `test_channels_telegram.py` | 消息归一化；按钮回调解析；发送失败重试 |
| e2e | 现有 `_FakeClient` 跑通「建 bot → 发消息 → 审批 → 产出」 |

---

## 7. 技术风险

| 风险 | 说明 | 对策 |
|---|---|---|
| MAF 私有 API | `_types` / `_middleware` / `_clients` 非公开 | 适配层 + 锁版本 + 契约测试 |
| 审批绑死 WS | 非网页触发时无人点按钮 | 落库 + 渠道按钮 + TTL |
| JSONL 并发写 | 多渠道同时写会错乱 | 单 session 串行队列 + 追加式写 |
| cwd 泄漏 | `discover_project_context()` 用进程 cwd | 改为 `bot.workspace` |
| 提示注入 | 渠道来信不可信 | untrusted 标记 + 工具白名单 + 强制审批 |
| Python 3.14 | 托管环境支持面窄 | 自带镜像，或评估降到 3.12 |
| 进程单点 | 崩溃后 routine 全停 | 守护进程 + 启动补偿 + 健康检查 |
