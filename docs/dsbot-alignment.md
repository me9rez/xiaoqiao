# 向 DeepSeek Bot（ds-bot）对齐

参考项目：<https://github.com/Fei2411/DeepSeek-Bot>（`README.zh.md`，v0.1 预览）。
本文是「前端按这个项目对齐、后端功能跟上」的总方案；每轮按里程碑推进，实施记录追加在 §5。

---

## 1. 参考项目是什么

ds-bot 是 **DeepSeek Harness 的插件**，把 dsh 改造成 bot 形态的产品。它不自己实现 agent 循环，
而是复用 dsh 的会话、工具、模型与插件系统；自己实现的是**产品层**：

| 层 | ds-bot 的实现 |
|---|---|
| 数据 | dsh 主目录下 `bot/`（bot、群、记忆、定时任务）+ `sessions/`（每个 bot 一个会话） |
| 后端 | `ds-bot/src/host/*`：roster（成员/角色）、groups（群聊调度与交接）、memory、usage、secrets、capabilities、schedules、turns |
| 前端 | `ds-bot/src/client/*`：约 55 个原生 JS 模块，`styles.js`（111KB CSS）；打包成 `client.js` 注入 dsh Web |
| 形态 | 单窗口 = 一个 bot；侧栏 = 主 bot + 群 + bot 列表；右侧抽屉 = bot 详情；设置是覆盖式对话框 |

我们（小巧）是**独立实现**：Python 网关 + Vue 前端，已有 bots / groups / runs / routines / channels /
memory / artifacts / usage / approvals 等仓储。所以对齐不等于照搬代码，而是**对齐产品面**：
同样的信息架构、同样的交互习惯、同样的必然后端能力。

---

## 2. 参考的信息架构（据 `docs/images/*.zh.png` 拆解）

### 2.1 侧栏（`team.zh.png`）

```
┌ DS Bot            [搜索] [+]
│
│ ┌──────────────┐        ← 主 bot 大卡片（emoji + 名字 + 职位徽标「总管」+ 星标）
│ │   🐳 Chief   │
│ │     总管     │
│ └──────────────┘
│
│ 🦉📊🔨 小团队              ← 群：成员 emoji 堆叠 + 名字 + 副标题（成员/技术栈）
│  程序员 · 技术栈：Astro + Mark…
│ 🧑‍💻 程序员          [2]    ← bot：emoji + 名字 + 副标题（一句话自我介绍）+ 未读/待办徽标
│  我是程序员，负责写代码和审…
│ 🔨 写手              [2]
│  我是写手，专职帮你写和改博…
│
│ [🐳]  ⚙ 连接插件 ①        ← 底部：身份 + 插件/引擎连接状态（红点=异常）
└
```

要点：
- **群与 bot 同列**，最近活跃的在上；每行两行文本（名字 + 一句话副标题），右侧是可点击的徽标。
- **主 bot 单独一张大卡片**，带职位徽标与星标；它是「有问题找它」的入口。
- 侧栏**没有**「工具箱 / 自动化 / 运行记录 / 审批」这类顶级导航——它们都在设置里。

### 2.2 主区（`team.zh.png` / `group.zh.png`）

- 顶部**悬浮胶囊**：emoji + 名字（群里是成员 emoji 堆叠 + 群名）；进入详情时胶囊右侧出现 `←`。
- 消息流：
  - **bot 消息 = 浅灰气泡**，左上角一行「emoji + 名字」（群里）+ 角色徽标（`管理员`）；
  - **用户消息 = 深色填充气泡**，右对齐，大圆角；
  - **系统事件居中一行**：「已创建 🔨 写手」「已创建群聊 🦉📊🔨 小团队」；
  - **思考过程**折叠成一行灰字，点开才展开；
  - **@ 提及**渲染成带 emoji 的小胶囊（`@写手`）。
- 输入框：`+` | `给 <名字> 发消息` | 麦克风 | 蓝色语音按钮。`+` 里有「引用对话」。

### 2.3 Bot 详情抽屉（`details.zh.png`）

右上角 `⚙ / ⤴ / ✕`；大 emoji、名字、职位；`详情 | 浏览器` 分段；
分区依次是 **模型**（下拉卡片，显示 model + provider，空态「在 Bot 设置里添加说明」）、
**记忆**（`3 条` + `管理 >`）、**用量**（`69.3K tok · 缓存命中 83%`）、
**定时任务**（`还没有定时任务，去添加`）。

### 2.4 设置（`usage.zh.png` 背景）

覆盖式对话框：左栏 **通用 / Bot / 群聊 / 连接器 / 定时任务 / 用量 / 密钥 / 反馈** + 底部 `Harness 设置`。
右栏是当前分区，`✕` 关闭。不是独立路由页。

用量分区：时间范围分段（24 小时 / 7 天 / 30 天 / 12 周 / 12 个月 / 自定义）→ 四个 KPI
（Token、缓存命中率、输出、调用次数）→ **Token 走势堆叠柱状图**（按天，可切「按 Bot / 按模型」）→
Bot 榜（名字 + 职位 + 进度条 + 百分比）→ 模型榜。

### 2.5 产品机制（README）

| 机制 | 说明 |
|---|---|
| 主 Bot / Chief | 权限最高的 bot，能创建/修改其它 bot 与群；首次进入自带一个 |
| 群聊 | 必须设一个**管理员**；默认由管理员回复，管理员会去调其它 bot；`@` 直接找某个 bot；bot 之间也能 `@` 派活并同步进度 |
| 记忆 | bot 有记忆（Markdown 格式），会在下次工作时应用；详情页可管理 |
| 能力 | 团队共享的 MCP 服务 / 技能 / 能力包；在 Bot 设置里启用；本地 MCP 命令要用户批准；被他人使用的能力只有你或主 Bot 能改 |
| 引用对话 | 输入框 `+` → 引用另一段对话 |

---

## 3. 对照表（现状 → 参考）

> 状态列在 2026-10-18 逐行复核过一遍：✅ = 已交付（§5 有实施记录），⬜ = 未做，并写明是「有意不做」还是「待做」。

### 3.1 前端

| 面 | 原差距 | 状态 |
|---|---|---|
| 左侧 | 要重排：合并两栏、群与 bot 同列、副标题与徽标、连接状态 | ✅ M1 `1e92d24` |
| 顶部 | 要重做：悬浮居中胶囊 | ✅ M1 |
| bot 消息 | 要改：浅灰气泡 + 群内作者行 | ✅ M2 `cb1c0b2` |
| 用户消息 | 要改：深色填充气泡 | ✅ M2 |
| 系统事件 | 缺：居中事件行 | ✅ M2（群内系统消息居中） |
| 思考过程 | 微调：单行灰字 | ✅ M2 |
| @ 提及 | 补渲染：消息内胶囊 | ✅ M2 |
| 群内进度 | 部分有 → 要同步「它在做什么」 | ✅ M6 `906da4b`（显示具体哪个 Bot 在回复） |
| bot 详情 | 要重做分区：模型 / 记忆 / 用量 / 定时任务 | ✅ M3 `8dfcbc8` |
| 设置 | 要改形态：覆盖式对话框 | ✅ M4 `9452e9a`（左栏保留我们真实的 10 个页面，不硬造参考里的 8 项） |
| 用量 | 要重做：KPI + 堆叠柱状图 + Bot/模型榜 | ✅ M4 `d70687d` |
| 能力 | 要合并 + per-bot 启用 | ✅ M5 `b603b7c`（在 Bot 编辑器里，工具箱页保留为全局安装入口） |

### 3.2 后端

| 能力 | 原缺口 | 状态 |
|---|---|---|
| bot 角色/简介 | 需要 `role` + `description` | ✅ M5 `baac8b1`（schema v3） |
| 主 Bot | `is_main` 标记 + 权限（只有它能改别人的 bot/群） | ⬜ **有意不做权限**：派活/改组都由用户在 UI 直接操作，没有可拦截的执行点；`is_main` 目前由「第一个 Bot」推导（侧栏星标） |
| 群管理员 | 语义升级为「管理员」 | ✅ M5 `f516a6c`（`adminBotId` 别名，未新增列） |
| 未读/待处理徽标 | 需要 per-entity 未读 | ✅ M5 `fb76aa5`（本地已读时间；「待你处理」用 activity 状态） |
| 系统事件 | run 内事件写进消息流 | ✅ M2（群内系统消息已渲染；单聊目前无系统事件源） |
| bot 记忆 | 缺「管理入口 + Markdown 记忆文件」口径 | ✅ 已有 `memory_facts/notes` + 设置 → 记忆页 + 抽屉入口 |
| 能力（per-bot 启用） | 需要 bot ↔ 能力关联 | ✅ M5 `b603b7c`（`bot_capabilities`，执行处过滤 `mcp__*`） |
| 用量聚合 | 缺缓存命中率与按时间分桶 | ✅ M5 `8de27e1`（v4 加 `cache_read_tokens`、`by_day`/`by_bot`） |
| 引用对话 | 消息需要 `quoted` | ✅ `8030cb5`：`runtime/quotes.py` 把引用写进用户消息的 `additional_properties`（framework 在 `agent.run()` 内建消息，无钩子，故在 run 后附加，保持单一 transcript）；前端回读并渲染引用块，刷新后仍是引用 |
| schema 迁移 | 需要 ALTER 迁移器 | ✅ M5 `87c051c`（+ 6 项迁移测试 `e6b31b5`） |

---

## 4. 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M1 外壳** | 侧栏重排（主 bot 卡片 + 群/bot 同列 + 副标题/徽标 + 底部连接状态）、顶部改悬浮胶囊、导航链接收进设置入口 | 截图与 `team.zh.png` 同版式；lint/test/build 全绿 |
| **M2 消息流** | bot 浅灰气泡 + 作者行、用户深色气泡、系统事件居中、思考过程单行、@ 提及胶囊 | 群聊截图与 `group.zh.png` 同版式 |
| **M3 bot 详情抽屉** | 抽屉取代 ContextPanel 顶部分区：模型 / 记忆 / 用量 / 定时任务；空态文案对齐 | 与 `details.zh.png` 同版式 |
| **M4 设置与用量** | 设置改覆盖式对话框（左栏 8 项）；用量页 KPI + 堆叠柱状图 + 榜单 | 与 `usage.zh.png` 同版式 |
| **M5 后端补齐** | ALTER 迁移器；`bots.role/description/is_main`；`groups` 管理员语义；系统事件；未读计数 | pytest 覆盖，RPC 文档更新 |
| **M6 能力与交接** | 能力 per-bot 启用 + 主 Bot 权限；引用对话；群内进度同步 | 端到端 |

顺序说明：M1/M2 只动前端，最快见效；M5 是 M3/M4/M6 的前置数据，可视需要提前。

---

## 5. 实施记录

### M1 外壳（2026-10-18）

做了什么：

| 文件 | 改动 |
|---|---|
| `web/src/components/chat/Sidebar.vue` | 重写：品牌行（小巧 + 搜索 + 新建 + `⋯` 菜单）→ 主 Bot 卡片 → 群/Bot 同列 → 可折叠「最近对话」→ 底部「已连接引擎 + 设置」 |
| `web/src/components/shell/EntityRow.vue` | 新增：一行两段文本（名字 + 一句话副标题）、可选 emoji 或成员 emoji 堆叠、状态点、待处理徽标 |
| `web/src/components/chat/ChatHeader.vue` | 重写为居中悬浮胶囊：emoji（群里是堆叠）+ 名字 + 状态点，非首页时多一个 `←` |
| `web/src/views/ChatView.vue` | 去掉 64px 的 `BotRail`，侧栏接管 Bot 切换与编辑（双击） |
| `web/src/components/bots/BotRail.vue` | 删除（其 `handleSelect` 里引用了未导入的 `sessionsStore`，点第二个 Bot 会抛 ReferenceError） |

导航去向：工具箱 / 定时任务 / 运行记录 / 审批 从侧栏顶级项移入 `⋯` 菜单（参考实现把它们放在设置里；我们没有改动这些路由）。

副标题口径（**临时**，等 M5 的 `bots.role/description`）：
- Bot → `persona` 第一个非空行，截断 40 字；为空时退回模型名。
- 群 → 成员名前 3 个，超出补「等 N 个」。

回归：`vue-tsc --build` 0 错误、`vitest 102`、`pnpm build-only` 通过；Chromium 截图核对侧栏/胶囊/`⋯` 菜单。

#### 顺带修掉的一个真问题：`pnpm type-check` 一直是空转

`package.json` 里 `"type-check": "vue-tsc --noEmit"`，而根 `tsconfig.json` 只有 `references`、`files: []`——**它什么都没检查**。
改成 `vue-tsc --build` 后立刻暴露 8 个错误并全部修掉：

| 位置 | 问题 |
|---|---|
| `MessageList.vue` ×4 | 虚拟滚动实例的 `$el` 不在 `DynamicScrollerExposed` 类型里（补 `& { $el: HTMLElement }`） |
| `stores/chat.ts` / `ChatSessionView.vue` | `loadSession()` 参数写成 `MessageContent[]`，实际传的是 `Message[]` |
| `ProviderCard.vue` | `providers[id]?.api_key.length > 0` 在 `noUncheckedIndexedAccess` 下可能 undefined |
| `SettingsModelsView.vue` | 模板里直接索引 `providers[id]`，改为先配对成 `{ id, config }` |

### M2 消息流（2026-10-18）

| 文件 | 改动 |
|---|---|
| `web/src/components/chat/MessageItem.vue` | 重写：助手消息改浅灰气泡（`--color-surface`，左上角小圆角），用户消息改深色填充（`--color-send-bg` / `--color-send-icon`）；去掉每条的机器人头像，作者行改为可选 prop（群聊传入）；**思考过程折叠成一行**「▸ 思考过程」，点开才显示全文 |
| `web/src/views/groups/GroupView.vue` | 去掉与顶部胶囊重复的群头部（群设置改成右上角浮动按钮）；bot 消息加作者行「emoji + 名字 + 管理员 + 时间」；系统事件居中一行；**@ 提及渲染成胶囊**（只对真实成员生效，`@foo` 保持纯文本）；输入框占位改成「给 <群名> 发消息」 |

同时在后端修掉一个会让群聊直接不可用的问题：`_FakeClient.get_response` 是 `async def`，但框架的
`_agents._call_chat_client()` 在 `stream=True` 时**不 await**，直接对返回值调用 `.map()`——于是无 API key 时
群聊必然抛 `AttributeError: 'coroutine' object has no attribute 'map'`（之前只在群里触发，因为单聊走另一条路径）。
现在 `get_response` 是同步方法：流式分支直接返回 `ResponseStream`，非流式分支返回一个 awaitable；
`test_settings.py` 的用例相应改了断言，并新增一条「非流式返回 awaitable」。

另一个顺带修复：群聊运行结束时若回复为空，网关不会发任何消息，`groupsStore.sending` 会永远为 true（输入框卡在
「Bot 正在回复…」）。现在 store 同时监听 `done` / `error` 清掉该标志。

已验证：用户气泡、系统事件、顶部胶囊、侧栏行（含状态点）在 Chromium 里逐项核对；`vue-tsc --build` 0 错误、
vitest 102、pytest **282**、`pnpm build-only` 通过。
**未验证**：bot 气泡的作者行与 @ 胶囊——本机没有 API key，假客户端的流式文本没有变成回复
（`turn_end reason=complete` 但 `turn_text` 为空），需要真实模型才能看到；见 §6。

### M3 bot 详情（2026-10-18）

`web/src/components/chat/ContextPanel.vue` 顶部新增 Bot 详情区（对齐 `details.zh.png` 的分区与文案）：

| 区块 | 内容 | 数据源 |
|---|---|---|
| 身份 | 大 emoji + 名字 + 「主 Bot / 模型名」 | `botsStore.activeBot` |
| 模型 | `ModelPicker` 直接嵌在卡片里，切换会同时写 bot 的 `model` 与 `default_model` | `botsStore.update` + `settingsStore.setDefaultModel` |
| 记忆 | `N 条` + `管理 ›` → `/settings/memory` | `useMemoryStore.facts + notes` |
| 用量 | `12.3K tok · 8 次`（空态「暂无」） | `useUsageStore.summary.window`（按 bot 过滤） |
| 定时任务 | `N 个` 或「去添加 ›」→ `/routines` | `useRoutinesStore` 按 botId 过滤 |

原有的「进度 / 工作区 / 产物 / 操作记录」四段保留在下面，没有为了对齐而删功能。
未做：参考实现的 `详情 | 浏览器` 页签（浏览器子面板依赖 dsh 的 browser 插件，见 §7）；「缓存命中 %」已在 M5 补上。

回归：`vue-tsc --build` 0 错误、vitest 102、Chromium 截图核对。

### M4 设置与用量（2026-10-18）

**设置改覆盖式对话框**（`SettingsLayout.vue`）：整页布局换成 `fixed inset-0` + 遮罩 + 居中卡片（`max-w-4xl`、`max-h-[85vh]`），左栏是分区导航、右上是当前分区名与 `✕`（Esc 也能关，`router.back()`，无历史时回首页）。左栏顺序对齐参考：**通用 / 模型 / 频道 / 记忆 / 性格 / 安全 / 用量 / 诊断 / 反馈 / 版本**，下面隔一条线放两个「在对话框外」的入口（定时任务、工具箱）——参考也是这么把非设置项塞进同一栏的。
路由此刻只描述内容区，`/settings` 仍重定向到 `/settings/usage`。

**用量页**（`SettingsUsageView.vue` + `UsageRepository.by_bot()/by_day()`）：

| 区块 | 内容 |
|---|---|
| 范围 | 今日 / **7 天（默认）** / 30 天 |
| KPI ×4 | Token / 输出 / 调用次数 / 花费 |
| Token 走势 | 每天一列、按 bot 分段的堆叠柱状图 + 峰值 + **带 Bot 名的图例**（不只靠色块） |
| Bot 榜 | emoji + 名字 + 职位 + token + 占比 + 进度条 |
| 模型榜 | 模型 + token + 占比 + 进度条 |
| 今日预算 | token / 美元两条进度条（原有） |

`usageSummary` 新增 `byBot` 与 `byDay`；页面改成团队视角（不再按 `activeBot` 过滤），RPC 仍支持 `botId`。

「缓存命中率」KPI 在 M5 补上（见 §5 的 M5 表）。

### M5 后端补齐（进行中，2026-10-18）

| 项 | 状态 |
|---|---|
| schema 迁移器 | ✅ `store.MIGRATIONS` + `SCHEMA_VERSION = 3`（给 `bots` 加 `role` / `description`），`init_db` 按版本顺序执行、容忍手工加过列；6 项回归测试 |
| bot 职位/简介 | ✅ 数据类 → 行映射 → 序列化 → `create`/`update` → `createBot`/`updateBot` → TS 类型 → 侧栏副标题与详情抽屉 → Bot 编辑器输入框 |
| 群管理员 | ✅ 语义本来就在：`resolve_recipients()` 用 `default_bot_id` 决定谁应答并派活。**没有新增列**，而是把它按产品叫法暴露成 `adminBotId`（同一值），`updateGroup` 接受 `adminBotId`，群行副标题显示「管理员 X · 成员」，群内作者徽标改读它。3 项测试 |
| 未读标记 | ✅ 不做服务端计数：`utils/unread.ts` 记本地「最后打开时间」，`updatedAt` 更新后侧栏显示小圆点（读者属性，不是会话属性） |
| `UsageTotals` 的 cache token | ✅ schema v4 给 `usage_events` 加 `cache_read_tokens`；`record()`/`summary()` 带它，三条 run 路径都传 `event.cache_read_tokens`；`usageSummary` 输出 `cacheReadTokens`；用量页第二张 KPI 卡改「缓存命中率」（命中 = cacheRead / (input + cacheRead)），输出挪进 token 卡副标题 |
| 能力 per-bot | ✅ `bot_capabilities` 表只存「与默认不同」的开关（默认启用，避免老 Bot 突然掉工具）；`_tools_for()` 对关掉的连接器过滤 `mcp__<server>__*` 工具，改开关真的改行为；Bot 编辑器有「能力」分区 |
| 主 Bot 权限 | ⬜ 未做（谁能派活目前由模型自己 @ 决定，无强制点） |

---

### M6 能力与交接（进行中，2026-10-18）

| 项 | 状态 |
|---|---|
| 引用对话 | ✅ 消息操作行加「引用」→ 输入框上方引用条 → 发送时以 `> 引用 <name>：…` 并入 prompt 文本（引擎 un_turn 只收单串，无 per-message 字段）；用户气泡保留 `quoted` 供后续渲染 |
| 群内进度同步 | ✅ 群内发送时显示**具体是谁**在回复（读 activity store 的 working 成员，多于两个显示「A、B 等 N 个 Bot」），并显示最多 3 个 Bot 头像 |
| 引用服务端持久化 | ⬜ 未做：需要改运行时消息模型 |
| 群聊里的引用按钮 | ⬜ 未做 |

---

## 6. 已知问题

| 问题 | 影响 | 下一步 |
|---|---|---|
| 无 API key 时 `_FakeClient` 的流式文本没有变成回复（`turn_end reason=complete`，`turn_text` 为空） | 本机看不到任何 Bot 回复，群聊里 bot 气泡的作者行 / @ 胶囊也无法目视验证 | 查 `agent_runtime._stream()` 取文本的口径（fake 只用 `Content(type="text")`），或直接用真实 key 验证 |
| `groupsStore.sending` 依赖 `done` / `error` 兜底 | 多个群/会话同时跑时，任一 `done` 都会清掉标志（可能提前收起「正在回复」） | M5 把 `groupId` 带进 run 事件，按群匹配 |

---

## 7. 不做的部分

| 不做 | 原因 |
|---|---|
| 照搬 `client.js` / `styles.js` | 我们是 Vue + UnoCSS + token 体系，照搬会破坏 `docs/design.md` 的约束 |
| 语音/麦克风输入 | ds-bot 用浏览器 Web Speech；我们没有对应的产品需求，先不做 |
| 内置浏览器页签（`browser-pane.js`, 35KB） | 依赖 dsh 的 browser 插件能力；单独立项 |
| 「Harness 设置」直连 dsh | 我们不是 dsh 插件，等价物是现有 `/settings/*` 页面 |
| 主 Bot 的「只有它能改别人的 Bot/群」权限 | 我们的 Bot/群编辑都在 UI 上由你直接操作，服务端没有可拦截的越权路径；加一层假权限只会让 UI 说谎。真要做，得先有「多个用户/多个来源」才谈得上权限 |
| 硬复刻设置里的 8 个分区名（通用/Bot/群聊/连接器/密钥…） | 我们没有对应的独立页面，造空页比保留 10 个真实页面更糟；对齐的是**形态**（覆盖式对话框 + 左栏 + ✕），不是标签 |

---

## 8. 待办（复核后剩下的）

| 待办 | 为什么值得做 | 落点 |
|---|---|---|
| 群聊里的引用按钮 | 群里长对话更需要引用 | `GroupView` 的消息操作行复用 `MessageItem` 的引用动作，走 `groupMessages` 的 `quoted` |
| `_FakeClient` 流式文本不产出回复（§6） | 无 API key 时无法目视验证任何 Bot 回复 | `agent_runtime._stream()` 的文本取值口径 |
| run 事件带 `groupId` | 多个群同时跑时 `sending` 会被别人的 `done` 清掉 | `_emit(... group_id=...)` 已有，把前端匹配逻辑改成按群匹配 |
