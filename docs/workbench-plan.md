# 技术方案：把「工作台」体验补上（信息架构 / 教一遍 / 状态可见性）

> 状态：待评审 · 2026-10-18 · 基线 `39d70f9`
> 配套：[grok-bot-comparison.md](grok-bot-comparison.md)（对标调研）、[design.md](design.md)（**本文所有视觉方案受它约束**）、[protocol.md](protocol.md)
> 问题来源：三条差距——第一屏给什么、自动化的输入方式、状态的可见性。

---

## 0. 结论

三件事都做，但**不是三个独立功能，是同一个东西的三面**：现在的界面没有「现在」这个概念。
Bot 是有的、会话是有的、运行记录是有的，但它们散在三个地方，用户得自己去拼「谁在干什么、卡在哪、要不要我」。

所以顺序是：**先让服务端能回答「现在」**（M1），**再把它画出来**（M2/M3），**最后让「刚才做的那件事」能变成自动化**（M4/M5）。

| 改动 | 一句话 |
|---|---|
| ① 信息架构 | 不重排导航，把**首页从「空白输入框」改成「现在」视图**：按 Bot 分组列出正在跑 / 等你审批 / 刚完成的活 |
| ② 教一遍 | 一次成功的运行结束后出现**「存为定时任务」**：从 transcript 抽出工具调用序列，生成可编辑的步骤清单 + 调度，落进已有的 `routines` 表 |
| ③ 状态可见性 | 状态从**客户端 store** 搬到**服务端聚合 + 广播**，Bot 头像右下角三态点（空闲 / 在忙 / 等你），带文字与 aria |

工程量约 **6–8 人日**；不新增数据库表（只给 `routines` 加一列、给 transcript 行加一个字段）。

---

## 1. 现状证据（都核过代码，不是印象）

### 1.1 布局与第一屏

```
BotRail(48px) │ Sidebar(240px) │ main: ChatHeader + RouterView │ ContextPanel
```

- `web/src/views/ChatView.vue:88-106` 就是这个四栏结构。
- 首页 `chat-home` → `EmptyStateView`：一个居中的输入框 + 建议卡片，**没有任何「当前在发生什么」**。
- 侧边栏（`Sidebar.vue:219-258`）的导航是：工具箱 / 自动化 / 定时任务 / 运行记录 / 审批。五个入口平铺，没有「现在」这一项。

### 1.2 状态是客户端的，刷新即失忆

- `runState` 只存在于 `web/src/stores/chat.ts`（`'idle' | 'running' | 'waiting_approval'`），由 WebSocket 事件在前端累加。
- `BotRail.vue:18-27` 用它算「哪些 bot 在跑」，画一个 2.5px 的圆点；`Sidebar.vue:48-51` 用它决定会话行要不要转圈。
- **页面刷新后这些状态全空**——因为服务端从来没有「谁现在在忙」这个查询。
- 服务端其实有数据：`runs` 表有 `queued / running / waiting_approval / done / failed / cancelled`（`runtime/runs.py:25`），`listRuns` RPC 也在。缺的是**聚合视图与广播**。

### 1.3 自动化有两套，而且同名

| 表面 | 存储 | 谁写的 |
|---|---|---|
| `/routines`（侧边栏「定时任务」） | SQLite `routines` + `routine_fires`（`runtime/routines.py`），由 `Scheduler` 真正触发 | 这是**活的**那套 |
| `/automation`（侧边栏「自动化」，内含「定时任务」「监听事件」） | JSON 文件 `~/.xiaoqiao/automation/{scheduled_tasks,listeners}.json`（`automation.py`） | 独立实现，与 `routines` 无关联 |

同一个词「定时任务」指两个不同的东西，是这次要顺手清掉的债（见 §6）。

### 1.4 「教一遍」的原料已经有了

- transcript 落盘在 `~/.xiaoqiao/sessions/<sessionId>.jsonl`，**函数调用与结果都在里面**（`session.py:454` 处理 `function_call`，`486` 还原）。
- 但**行里没有 run 边界**：不知道哪几条消息属于哪一次 run。这是 M4 唯一需要动 schema 的地方。
- `routines` 表已有 `schedule_json` / `prompt` / `target_group_id` / `target_channel_id`，能直接承接「存下来的流程」。

---

## 2. ① 信息架构：第一屏给「现在」

### 2.1 三个候选

| 方案 | 做法 | 代价 | 判断 |
|---|---|---|---|
| A 重排 | 把 Bot 竖轨改成可展开左栏，Bot 列表升为一等 | 大：动导航骨架、动 keep-alive、动全部快捷键 | ❌ 收益不匹配 |
| B **「现在」视图** | `chat-home` 变成 Now：按 Bot 分组的三条带（在忙 / 等你 / 刚完成），空时回落到现在的输入框 | 中：一个新视图 + 一个聚合 RPC | ✅ **推荐** |
| C 轻量带 | 在现有首页顶部加一条「在忙的 Bot」 | 小 | ⚠️ 只能算 B 的子集，单独做意义不大 |

**为什么选 B**：BotRail 已经很克制（48px、双击编辑、hover 铅笔），这套交互没出问题；问题在「点进来之后看到什么」。B 不动导航、不动路由骨架，只换 home 的内容，风险最低而命中最准。

### 2.2 Now 视图的信息结构

```
┌ 等你（1）────────────────────────────────┐
│ ● 研究员   卡在审批：run_command(cp -r …)  [去处理]  │
├ 在忙（2）────────────────────────────────┤
│ ● 写手     正在写：write_file(docs/周报.md)  [看进度] │
│ ● 财务     已跑 4 分钟                       [看进度] │
├ 刚完成（3）──────────────────────────────┤
│ ✓ 研究员   12:41 完成「本周竞品摘要」       [看结果]  │
└────────────────────────────────────────┘
[ 把你的第一句话交给谁？▾ 输入框 ]
```

规则：
- 分组顺序固定 **等你 > 在忙 > 刚完成**；组内按 `started_at` 倒序。
- 「等你」必须是一等公民（它是唯一需要用户动作的状态），排第一且带数量徽标。
- 每条都可点，直接进对应 session 或审批详情。
- **无活动时整块隐藏**，回落到现在的 `EmptyStateView`（不破坏现有体验）。

### 2.3 触点

- 首页 `chat-home`（主要）。
- 审批徽标已经存在（`Sidebar.vue:251-257`），保持不变。
- 桌面场景：`desktopShell.ts` 的通知已按 `document.hidden` 节流；Now 视图的「等你」与它同源，不重复造。

---

## 3. ② 教一遍：把这次运行存成定时任务

### 3.1 交互

```
[一次 run 正常结束]
  ↓ 会话末尾出现一行轻量操作
  这次跑得不错？ [存为定时任务]
  ↓ 打开预填好的编辑器
  ┌ 名称：  本周竞品摘要
  ├ 什么时候： 每周一 09:00        （从 schedule 预设里选，不要求写 cron）
  ├ 步骤清单：（来自这次运行，可删可改）
  │   1. read_file(docs/竞品清单.md)
  │   2. run_command(python scripts/fetch.py)
  │   3. write_file(docs/竞品摘要.md)
  └ 交付到：当前会话 / 群聊 / 频道
  [存下来]
```

**语义要写清楚**：存的是「这次**做了哪几步**」+「交给谁 + 什么时候」，**不是录屏重放**。

### 3.2 为什么 v1 不做「参数原样重放」

| 顾虑 | 说明 |
|---|---|
| 参数会过期 | `run_command` 里常带路径/时间戳，`http_fetch` 带 URL，下一次跑可能指向已经不存在的文件 |
| 副作用不可逆 | 重放 `write_file` / `run_command` 等于让机器在你不在时重复写盘、跑命令 |
| 我们的执行面不同 | Grok 的重放建立在「云电脑 GUI」上（它记录的是点击与输入）；我们是命令行 + 文件，重放粒度更粗、更危险 |
| 审批语义 | 重放的每一步仍要走审批，那「自动」就名不副实 |

所以 v1 产出的是**结构化的提示词**：步骤清单渲染进 `prompt`，模型每次自己决定怎么走；`steps_json` 存下来是为了以后做「受控重放」（只重放只读工具）与审计展示。

### 3.3 数据流

```
run 结束（runs.status = done 且 tool_calls > 0）
  ↓ 前端「存为定时任务」
  ↓ RPC: draftRoutineFromRun { runId }
  ↓ 服务端：从 transcript 切出该 run 的消息 → 提取 function_call 序列
  → 返回 { name, prompt, steps: [{tool, argsSummary}], suggestedSchedule }
  ↓ 用户确认/改
  ↓ RPC: createRoutine { botId, name, schedule, prompt, steps }
  → 落 SQLite routines（新增 steps_json 列）
```

### 3.4 run 边界怎么切（M4 的硬骨头）

当前 transcript 行没有 run_id。两个选项：

| 方案 | 改动 | 风险 |
|---|---|---|
| **A. 行上加 `runId`**（推荐） | `session.py` 写 JSONL 时带 `run_id`；`runs.begin()` 的 id 传进 turn | 旧行没有该字段：读取时若缺 `runId`，按 `created_at` 时间邻近归属 |
| B. 新增 `run_events` 表 | 新表 + 迁移 | 更重，且与 transcript 两份真相 |

**A 的最小实现**：`run_id` 作为 `TurnRunner` 的入参之一（网关在 `runs.begin()` 之后已经能拿到），`session.append_*` 落盘时写进每行。读取侧 `load_transcript` 保留该字段。

### 3.5 步骤抽取

只认 `function_call` 内容（`Content(type="function_call")`），每个转成：

```json
{ "tool": "write_file", "args_summary": "docs/周报.md", "call_id": "…" }
```

- `args_summary` 的取法：按工具白名单挑一个「人类可读字段」（`path` / `command` / `query` / `url`），截断到 80 字符；**存摘要不存完整参数**，避免把密钥/长文本带进 routine。
- 过滤掉只读探索（`list_files` / `search`）？**不过滤**，但 UI 默认折叠它们，因为「教一遍」的直觉里探索也是步骤的一部分。

---

## 4. ③ 状态可见性：服务端出「现在」

### 4.1 状态模型（四态，够用且不暧昧）

| 状态 | 判定（按优先级） | 视觉 | 文案 |
|---|---|---|---|
| `needs_you` | 任一 run `waiting_approval` | 警告色实心点 | 「等你审批」 |
| `working` | 任一 run `running` / `queued` | 强调色（脉冲，尊重 `prefers-reduced-motion`） | 「正在忙」 |
| `error` | 最近 5 分钟内有 `failed` | 危险色 | 「出错了」 |
| `idle` | 其余 | 无点 | — |

设计规范硬约束（`design.md` §9/§10）：**不能只靠颜色区分状态**，必须配文字或图标；状态色要「底色 + 边框 + 文字」成套。所以头像上的点只是提示，`title` + `aria-label` 必须有完整句子（例如「研究员正在忙：write_file(docs/周报.md)」）。

### 4.2 服务端：一个聚合查询 + 一条广播

**新 RPC `getActivity`**（snake_case 留给配置，RPC 沿用 camelCase）：

```json
{
  "bots": [
    { "botId": "bot_1", "state": "needs_you", "runId": "run_x", "sessionId": "s_1",
      "title": "本周竞品摘要", "currentTool": "run_command",
      "startedAt": "…", "lastFinishedAt": "…", "lastFinishedTitle": "…" }
  ],
  "pendingApprovals": 1
}
```

实现就在网关里：`self._runs.list(status="running")` + `list(status="waiting_approval")` + 最近失败，按 `bot_id` 聚合。**不新增表**。

**广播**：网关在 run 的三个人生节点（`begin` / 等待审批 / `finish`）`_broadcast({"type": "activity", "bots": [...]})`。
现在只有 `approval_requested` / `approval_resolved` 有广播，run 状态变化全靠前端自己推。补上之后**多端一致、刷新不掉**。

### 4.3 前端

- `stores/activity.ts`：订阅 `activity` 事件 + 首次 `getActivity`；`stateOf(botId)` 供各处读。
- `BotRail.vue`：现有的 2.5px 点改为三态组件 `<BotStatusDot :state>`；「等你」加一圈呼吸光晕（`prefers-reduced-motion` 下静态）。
- `Sidebar.vue`：会话行的 `Loader2` 换成同一组件，保证「头像与行」同源同色。
- `chat.ts` 里那份 `runState` **保留但降级为「当前会话的即时态」**，不再作为全局真相（避免两处打架）。

---

## 5. 里程碑

| 里程碑 | 内容 | 出口判据 | 人日 |
|---|---|---|---|
| M1 | `getActivity` RPC + run 三节点广播 + 单测 | 刷新页面后头像状态仍正确；两个客户端同时在线看到同一状态 | 1 |
| M2 | `BotStatusDot` + BotRail/Sidebar 接入（design token 成套 + aria） | 三态肉眼可辨；键盘可达；`prefers-reduced-motion` 下不抖 | 1 |
| M3 | Now 首页（等你 / 在忙 / 刚完成 + 空状态回落） | 有活动时首页首屏出现该 Bot 正在干的活，一条点击直达 | 1.5 |
| M4 | transcript 行加 `runId` + `draftRoutineFromRun` + 存为定时任务入口 | 一次带 3 个工具调用的 run 能一键生成草稿，名称/步骤/调度都正确预填 | 2 |
| M5 | `routines.steps_json` + 执行时渲染步骤清单 + 合并重复的 automation | 定时触发时 prompt 含步骤清单；`/automation/tasks` 与 `/routines` 只留一个 | 1.5 |
| M6 | 文档（product.md 三处、protocol.md、status.md）与回归 | pytest/vitest/type-check/两种构建全绿 | 1 |

M1–M3 与 M4–M5 之间**没有依赖**，可以先做状态与首页，再做「教一遍」。

---

## 6. 顺带要清的债（不做会让新功能长在歪处）

1. **两套自动化同名**（§1.3）：`/automation` 的 JSON 定时任务与 `/routines` 的 SQLite routines 合并到后者，前者只保留「事件监听」。否则「存为定时任务」到底存哪边会成为新的困惑源。
2. **侧边栏仍用旧 token**：`Sidebar.vue` 里大量 `var(--bg-card)` / `var(--border)` / `var(--text)`，违反 `design.md`「新代码只用 `--color-*`」。M2 动到这些行时顺手换掉。
3. **`ChatHeader` 的连接状态点**用 `bg-green-500` / `bg-red-500` 硬编码颜色（`ChatHeader.vue:54`），也违反「不写死十六进制」。M3 顺手改成状态 token。

---

## 7. 风险

| # | 风险 | 对策 |
|---|---|---|
| R1 | 状态抖动：短 run 让头像闪一下 | 客户端对 `working` 设最小展示 800ms；聚合端做 300ms 去抖 |
| R2 | 广播风暴：群聊里多个 bot 连续跑 | `activity` 按 bot 聚合成一条，最多 4 条/秒 |
| R3 | 旧 transcript 没有 `runId` | 读取侧按时间邻近归并；只对「新产生的 run」开放「存为 routine」 |
| R4 | 步骤清单泄露敏感参数 | 只存摘要字段 + 80 字符截断；写入前过一遍「像密钥就不存」的规则 |
| R5 | Now 视图在 0 活动时变成空白页 | 无活动整块不渲染，回落到现有 `EmptyStateView` |
| R6 | 动 UI 时破坏 keep-alive / 路由 | M3 只改 `chat-home` 的内容，不动路由表 |

---

## 8. 待确认决策

| # | 决策 | 推荐 | 备选与代价 |
|---|---|---|---|
| D1 | 第一屏 | **Now 视图替换 chat-home 的内容，空时回落** | 重排导航骨架：收益小、回归面大 |
| D2 | 「教一遍」的语义 | **半自动：生成可编辑步骤清单，不原样重放** | 全自动重放：危险，且与审批语义冲突 |
| D3 | 步骤清单存哪 | **`routines` 新增 `steps_json` 列** | 拼进 `prompt`：省一列，但没法审计/受控重放 |
| D4 | 状态的态数 | **四态**（needs_you / working / error / idle） | 两态：就是现在的样子，说不出「卡在哪」 |
| D5 | 合并两套自动化 | **合并到 routines** | 保留两套：新增的「存为 routine」会撞上同名概念 |

---

## 9. 不做什么

| 不做 | 原因 |
|---|---|
| 左侧 Bot 列表大重排 | 现有 rail 交互没坏，收益不抵回归面 |
| 录制 GUI 操作并重放 | 我们没有 GUI 执行面（也不想要），见 §3.2 |
| 自动把「重复出现的对话」推断成 routine | 需要行为聚类，误判成本高；先让用户显式点一次 |
| 改审批的交互与数据模型 | 审批已经是全仓最完整的一块，只做入口提级 |
| 移动端适配 | 与「跑在你机器上」冲突，另行立项 |

---

## 10. 实施记录（2026-10-18，M1–M5）

### 10.1 落地

| 里程碑 | 文件 | 说明 |
|---|---|---|
| M1 | `gateway/ws_server.py` | `getActivity` + `activity` 广播；`RunRepository(on_change=...)` 在 begin/set_status/finish 时通知网关 |
| M2 | `web/src/components/bots/BotStatusDot.vue`、`stores/activity.ts` | 三态点（等你/在忙/出错）+ `title`/`aria-label`；BotRail 与 Sidebar 共用 |
| M3 | `web/src/views/NowView.vue` | 首页改为「等你 / 需要看一眼 / 在忙 / 刚完成」，无活动回落到原空状态 |
| M4 | `gateway/ws_server.py`、`runtime/runs.py`、`store.py` | run 期间捕获工具调用（`run_steps` 表）、`draftRoutineFromRun` RPC、Now 视图的「存为定时任务」入口 |
| M5 | `runtime/routines.py`、`store.py`、`router/index.ts` | 步骤随 routine 落库（`routine_steps` 表）、触发时渲染进 prompt、`/automation/tasks` 重定向到 `/routines` |

### 10.2 与方案的偏差（都是实施时撞上的现实）

1. **步骤改成「运行时捕获」，不是「给 transcript 行加 runId」。**
   方案 §3.4 假设 transcript 是按轮追加的；实际 `turn_runner.py:105` 每轮都把 `session.messages`
   **整体重投影**自框架 session（`session.messages = [message_to_dict(m) for m in runtime.transcript]`），
   没有稳定的 per-message 身份可以打标。改为在 `_emit` 里从 `ToolCallStartEvent` 直接捕获 `(tool, args_summary)`，
   run 结束时写入 `run_steps` 表 —— 更准确，也不用动 transcript。
2. **`routine_steps` 独立表，不是 `routines.steps_json` 列。**
   `store.py` 只有 `CREATE TABLE IF NOT EXISTS` + 版本号，**没有 ALTER 迁移**；
   给已有库加列不会生效。新表在每次 `init_db` 时自动创建，老库无缝。
3. **`_fire_routine` 补了私有会话投递。**
   原来没有 group 目标的 routine 只打一行日志（"nothing to deliver"），
   而「从私聊里存下来的任务」正好没有 group —— 那样存了也不跑。现在无 group 时投进该 Bot 自己的会话。

### 10.3 验证

- `uv run pytest -q` → **266 passed**（新增 `test_activity.py` 9 项、`test_routine_draft.py` 10 项）
- `uv run pyright` 0 errors；`ruff check` / `format --check` 干净
- `pnpm type-check` 通过；`pnpm test:unit --run` → **84 passed**；`pnpm build` 通过

### 10.4 遗留

- 步骤清单在模态框里只随草稿保存，**没有单独的编辑 UI**（可以在 routine 创建后通过更新 prompt 间接改）。
- 「存为定时任务」入口目前只在 Now 视图的「刚完成」行；会话页内的入口留待下一步。
- 事件监听（`/automation/listeners`）仍走 JSON 存储，这次只合并了「定时任务」这一半。
