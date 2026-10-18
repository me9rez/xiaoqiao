# 对标校准：Grok Bot 到底长什么样（2026-10 调研）

> 目的：`docs/product.md` §4/§5 对 Grok Bot 的描述写于产品发布之前，其中「住在 X 上」这句话是错的。
> 本文用官方来源重绘它的对象模型与核心循环，并逐项对齐小巧的现状。
> 抓取时间 2026-10-18；来源见文末。

---

## 1. 事实：Grok Bot 是什么

**是一个桌面 App + 一台云端电脑 + 一组常驻 Bot**，不是什么「X 上的机器人」。

| 项 | 事实 |
|---|---|
| 首发 | 2026-08-11 beta，面向 SuperGrok Heavy / Cursor Ultra / Cursor Teams Premium |
| 形态 | macOS / Windows / Linux 原生安装包；移动端另有 App |
| 计费与账号 | 走 Cursor 账号体系（个人 Cursor 付费计划 / Cursor Teams / 绑定的 SuperGrok 订阅），企业另有销售流程 |
| 核心资产 | **每个账号一台共享云电脑**：能登录你的 SaaS、用你的浏览器会话、跑软件、管文件 |
| 2026-08-29 | 接通 X：可连 X 账号、给免费的 X API 额度，装 X 插件；`@bot` 可在 X 上接活 |
| 2026-09-03 | 推出企业版（两周免费试用），强调隔离环境与访问/网络/审计控制 |

### 1.1 五个一等对象

官方设计文里写得很清楚：**Bots**（常驻 agent）、**Chats**（对话面）、**Prompts**（上下文指令）、
**Tools**（连接软件与数据）、**Artifacts**（文档、代码等产出）。

### 1.2 核心循环：教一遍 → 它自己跑

这是它的留存机制，也是我们目前完全没有的一环：

> 「Ask a Bot to follow along as you complete a workflow once. It saves it as a routine and runs it on its own next time.」
> —— x.ai/bot 首页「Show a Bot how it's done」

即 **teach-by-demonstration**：用户手动做一遍，Bot 跟着看，把过程存成 routine；下次自己跑。
再往后是「存成 skill」与「交给另一个 Bot 接手」。

### 1.3 交互与控制

- **三级介入**：monitor（看它干）→ preview workspace（看它的工作台）→ take over（接管）。接管主要用于登录、验证码、两步验证这类必须人类的动作。
- **头像即状态灯**：idle / working / 需要你帮忙，靠头像本身表达。
- **群里协作**：把几个 Bot 放进同一个线程，它们自己传活；典型角色是 **Chief of Staff**（协调其他 Bot 的那个）。
- **审批**：外部变更前停下等人；企业版还有隔离环境与审计。
- **输入方式**：文字、语音输入（`Cmd/Ctrl+D` 听写）、语音通话。

### 1.4 生态与入口

- **Bot Marketplace**（`/bot/marketplace`）：预置角色，如 Sales Outbound、Talent Scout、Expense Manager、Chief of Staff……
- **Plugin / Connect apps**：OAuth 连接外部服务，例如 X 插件（搜帖、读时间线、看提及、趋势、书签）。
- **`@bot` on X**：在 X 上 tag `@bot` 把帖子交成任务；Bot 只在 X 上回一句确认，**活和结果都留在 App 里**。部分地区不可用（澳、英、EU、冰岛、列支敦士登、挪威）。

---

## 2. 我们 `product.md` 里已经过时的三句话

| 位置 | 现在写的 | 实际 | 影响 |
|---|---|---|---|
| §5 一句话定位 | 「Grok Bot 住在 X 上，小巧住在你的机器上」 | Grok Bot 住在**它的云端电脑 + 桌面 App** 里；X 只是 2026-08-29 才接上的一个入口 | 定位句是我们对外讲的招牌，这句话会让人以为它是社交机器人，而它卖的是「替你操作软件的同事」 |
| §4 七块能力 | 有「@bot on X」「操作电脑与应用」，但**漏了「教一遍→routine」与「共享云电脑/接管登录」** | 这两块才是它的核心循环与控制模型 | 漏掉「教一遍」，就等于没看懂它为什么让人上瘾 |
| §5 差异点表 | 「能力边界：平台给的 vs 你的文件系统、桌面、脚本」 | Grok Bot 也有能跑软件的云电脑 | 真差异不是「有没有电脑」，而是**电脑在谁家、装着谁的东西、数据落在哪** |

---

## 3. 逐项对齐（Grok Bot vs 小巧现状）

「我们有」以本仓库代码为准（`web/src/router/index.ts`、`python/src/xiaoqiao/`）。

| 维度 | Grok Bot | 小巧 | 结论 |
|---|---|---|---|
| 常驻 Bot | 有，创建时给「名字 + 一个主要职责 + 怎么干活」 | 有（`bots.py`：人格 / 模型 / 工具白名单 / 工作目录） | ✅ 基本对齐；我们多了「模型可选」，少了「 marketplace 的预置角色」 |
| 对话 | Chats | 私聊 + 群聊（`/chat`、`/g`） | ✅ 对齐 |
| 多 Bot 协作 | 同一线程传活，Chief of Staff 协调 | 群聊 + `@` + 交接（`runtime/group_chat.py`） | ⚠️ 有机制，没有「协调者」这个角色概念 |
| 自动化 | **教一遍存成 routine** + 定时/事件 | 定时任务（cron）+ 事件监听（`/automation`） | ❌ **缺 teach-by-demo**；我们的 routine 要用户自己写 |
| 技能 | 从跑过的流程存成 skill | SKILL.md 目录 + 列表/卸载（`/toolbox/skills`） | ⚠️ 能用，但只能自己写文件，不能「存下来」 |
| 记忆 | 每 Bot 独立记忆，UI 里能看到「Updated memory for X」 | 每 Bot facts + 会话摘要，`SettingsMemoryView` 可增删 | ✅ 对齐（我们的更显式） |
| 产物 | Artifacts：文档、代码、可预览可回传 | 工作区扫描 → 产物托盘 → 可发到频道（`runtime/artifacts.py`） | ✅ 对齐 |
| 审批 | 外部变更前停；三级介入 | 审批落库 + TTL + 任一入口可批（`runtime/approvals.py`） | ✅ 审批更强；❌ 没有「接管电脑」这一级 |
| 操作电脑 | 云端电脑：登录 SaaS、浏览器会话持久、可接管 | 只有 shell + 文件工具；Playwright 桌面自动化在 `status.md` 里是「明确后置」 | ❌ **最大能力缺口**（但也是我们刻意的边界：不碰 GUI） |
| 入口 | 桌面 App + iOS/Android + X 上的 `@bot` | Web + tinyjs 桌面外壳 + Telegram 频道 | ⚠️ 少移动端、少 IM 之外的社交入口 |
| 生态 | Marketplace + OAuth 插件 | MCP 连接器（stdio/http）+ 内置连接器列表 | ⚠️ 方向对，规模差很远 |
| 身份可见性 | 头像即状态灯（idle/working/需要帮忙） | 会话行上的一个小圆点（`runState`），Bot 头像本身不带状态 | ❌ **体感差异明显** |
| 上手 | 引导式：问你用什么工具 → 推荐第一批 Bot | 首次启动只有默认 Coder Bot | ❌ 缺 onboarding |
| 语音 | 听写 + 语音通话 | 无 | ❌ 无 |
| 自托管 / BYO 模型 | ❌ 云托管、绑定 Grok 模型 | ✅ 本机跑、任意 OpenAI 兼容模型 | ✅ 我们的真差异 |

---

## 4. 我的判断：你那句「感觉不一致」大概来自这三点

**① 信息架构的重心不一样。**
Grok Bot 是「一个 App，左边一排 Bot，点进去就是这个 Bot 正在干的活」；我们是「工作区 → 会话 → 侧边栏轨道 → 一堆设置页」。
我们的信息架构更像 IDE/运维台，它更像「同事的工作台」。这不是功能多少的问题，是**第一屏给什么**的问题。

**② 自动化那一环的「输入方式」不一样。**
Grok 让用户**做一遍**就得到一条 routine；我们让用户**写一条 cron + 一段 prompt**。
同样是 routine，一个面向不会写配置的人，一个面向会写的人。我们在这一步把非技术用户筛掉了。

**③ 状态的可见性不一样。**
它的 Bot 头像是状态灯；我们的状态藏在会话行的圆点里，而且只有 `running` / `waiting_approval` 两种。
「它现在在干嘛、卡在哪、要不要我」这件事，它做成了第一眼可见，我们做成了要去找。

---

## 5. 建议（按「抄得起 / 不该抄」分）

### 值得做，且不需要改架构

| # | 动作 | 代价 | 收益 |
|---|---|---|---|
| 1 | **Bot 头像带状态**（idle / working / 等审批 / 出错），侧边栏与 Bot 轨道通用 | 小：`runState` 已在 store 里，只差一个视觉层 | 直接补上「第一眼知道它在干嘛」 |
| 2 | **「教一遍」最小版**：把「这次运行的工具调用序列」存成 routine 草稿，让用户确认后落库 | 中：要记录 run 内的工具序列（`runs` + events 已有），并给一个「存为 routine」的入口 | 补上核心循环，且天然复用我们已有的 run 记录 |
| 3 | **首次启动向导**：问「你主要用它做什么」→ 生成 2–3 个预置 Bot（人格 + 工具白名单） | 小：`bots.py` 的 create 已够用 | 降低空状态焦虑 |
| 4 | **修 `product.md` 的三句话**（§2 表） | 极小 | 定位不再讲错对象 |

### 值得做，但要先想清楚

| # | 动作 | 顾虑 |
|---|---|---|
| 5 | 语音输入（先做听写，不做通话） | WebView 里 `MediaRecorder` 可用，但要一个转写服务；自托管语境下得让用户自带 key |
| 6 | 移动端 | 与「自托管在你机器上」冲突：手机要么走内网穿透，要么走一台常开服务器 |

### 不该抄

| 不做 | 理由 |
|---|---|
| 云端共享电脑 + 「接管登录」 | 那是它的护城河也是它的合规负担；我们的差异点恰恰是「不上传、不代登录」 |
| Bot / 插件 marketplace | 有供给侧才有 marketplace，我们连需求侧都还没稳定 |
| Cursor 账号与订阅制 | 我们是自托管；计费模型不在同一维度 |
| X 上的 `@bot` | 需要 X API 额度与账号绑定；我们已经有 Telegram 频道这一条够用的入口 |

---

## 6. 不确定 / 需要继续核实的

- 官方定价页只抓到了「Premium $3」这一行（页面被截断），个体/团队档位的完整价格没有确认，本文不引用具体金额。
- 「Prompts」作为一等对象的具体形态（是独立库、还是 Bot 配置里的字段）官方设计文只提了名字，没有展开；我们的对应物是 persona + `system_prompt.py` 的拼装，是否等价还没法判断。
- 移动端与桌面端的功能差异（能否完整跑 routine）没有核实。

---

## 7. 来源

- [Meet Grok Bot（产品页）](https://x.ai/bot) — 定位、teach-a-task、Bot 角色列表、marketplace 入口
- [Grok Bot now works with X（2026-08-29）](https://x.ai/news/grok-bot-and-x) — X 集成、X 插件、X API 额度
- [Tag @bot on X（官方文档）](https://docs.x.ai/grok-bot/tag-on-x.md) — `@bot` 的工作方式、地区限制、失败原因
- [Get started（官方文档）](https://docs.x.ai/grok-bot/get-started.md) — 桌面三平台、Cursor 账号、共享电脑、Take over 登录、语音输入
- [xAI Redefines Persistent AI Agents with Grok Bot（2026-09-03）](https://blockchain.news/news/xai-redefines-persistent-ai-agents-grok-bot) — 五个一等对象、三级介入、头像状态、Chief of Staff
- [xAI Launches Grok Bot, Always-On AI Teammates（2026-08-11）](https://blockchain.news/news/xai-launches-grok-bot) — 首发时间、cloud-based computer、群聊协作
- [xAI Unveils Grok Bot for Enterprises（2026-09-03）](https://blockchain.news/news/xai-grok-bot-enterprise-launch) — 企业版、隔离环境与审计
