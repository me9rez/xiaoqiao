# 实施状态审计

> 日期：2026-10-18 · 基线：`docs/pivot-plan.md`（v2）+ `docs/product.md`
> 本文逐条核对计划的交付定义与里程碑验收标准，并区分「已实现」「有意偏离」「明确后置」。

---

## 1. 交付定义（pivot-plan §0）

| # | 定义 | 状态 | 证据 |
|---|---|---|---|
| 1 | 对话由 Bot 发起，人格/模型/工具/工作目录彼此隔离 | ✅ | `bots.py` CRUD、`BotEditorModal` 工具白名单、`_tools_for()` 过滤、`test_bots.py` |
| 2 | Bot 群聊：`@` 指定应答、Bot 交接、跳数与防环 | ✅ | `runtime/group_chat.py`、`runtime/group_messages.py`、`test_group_chat.py`（交接、跳数、自触发、失败） |
| 3 | Run 可由 Web / Telegram / Routine 触发，关掉浏览器仍在跑 | ✅ | `RunRepository` 四种 trigger；`Scheduler`；`channels/telegram.py` + 网关接入 |
| 4 | 审批落库、TTL、任一入口可批、仅人类可批 | ✅ | `runtime/approvals.py`（TTL/冲突/过期/forbidden）、`ApprovalsView`、Telegram inline keyboard |
| 5 | Web UI 信息架构与 Grok Bot 对齐 | ✅ | Bot 轨道、群聊/私聊分区、`/approvals`、`/routines`、`/runs`、产物托盘 |

---

## 2. 里程碑（pivot-plan §11）

| 里程碑 | 验收标准 | 状态 |
|---|---|---|
| M0 契约冻结 | 类型与错误码一致 | ✅ 协议方法已实现，前端类型对齐 |
| M1 多 Bot 闭环 | 两 Bot 隔离、关网页 run 继续、刷新可恢复 | ✅ |
| M2 群聊 + 主动性 | 建群拉 3 Bot、`@` 应答、交接 ≤3 跳、9:00 日报进群、Bot 审批被拒 | ✅（调度 20s tick + `routine_fires` 去重 + 补跑） |
| M3 渠道 | Telegram 群多 Bot 互 @、收文件、按钮审批 | ✅（长轮询、4096 分片、sendDocument、callback → broker） |
| M4 记忆 + 交付 | 跨会话记得偏好、产物可预览可发送 | ✅（facts + FTS + 会话摘要；产物托盘 + 绑定频道自动发送） |
| M5 加固 | CI 绿、预算与限流生效、备份可恢复 | ✅（`.github/workflows/ci.yml` 在 GitHub Actions 上**实际通过**：python 与 web 双 job 全绿，含 lint/format/pyright/pytest/type-check/vitest/build。token/美元双阈值预算门禁 + 每分钟请求限流；`runtime/backup.py` 备份 agent.db/settings/sessions 并支持校验，沙箱后置） |

---

## 3. 功能清单（对照协议表）

已实现 RPC（camelCase 命名）：

```
bots:      listBots / createBot / updateBot / deleteBot
groups:    listGroups / createGroup / updateGroup / deleteGroup / addGroupMember / removeGroupMember
messages:  listGroupMessages
runs:      listRuns / getRun
approvals: listApprovals / resolveApproval / approval_response
routines:  listRoutines / createRoutine / updateRoutine / deleteRoutine / toggleRoutine
channels:  listChannels / createChannel / updateChannel / deleteChannel / testChannel
memory:    listMemory / upsertMemory / deleteMemory / addMemoryNote / searchMemory
artifacts: listArtifacts
usage:     usageSummary
misc:      listTools / previewPrompt / prompt / cancel / listSessions / ...
```

---

## 4. 有意偏离

| 计划 | 实际 | 原因 |
|---|---|---|
| `RunManager` 接管全部执行（队列、并发上限） | 网关用 `RunRepository` 记录 run，`RunManager` 已实现并有测试但未接入主路径 | 先保证 run 记录、审批关联、事件 `runId` 统一；队列化属于内部重构，无用户可见差异，避免在功能推进期引入回归 |
| 协议表里的 `runs.cancel` | 取消通过既有 `cancel {sessionId/groupId}` 实现 | 记录态 run 无独立任务句柄，语义等价 |
| 记忆摘要调用模型 | 采用确定性摘要（最近 5 条用户请求，≤400 字） | 零成本、离线可测；存储契约与 LLM 摘要一致，可平滑替换 |

---

## 5. 明确后置（product.md P4「按需」）

- Docker 沙箱执行器（product.md D6：接口先留、实现后置）
- Playwright / 桌面自动化
- 多租户与账号体系（product.md D8：已从范围移除，回归远期评估）
- 移动端、X DM
- 单用户鉴权与公网部署加固
- 备份已有实现（`runtime/backup.py`），但尚未提供 CLI 子命令；恢复按「拷贝回状态目录」执行

---

## 6. 验证（2026-10-18）

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端单测 | `uv run pytest -q` | **192 passed**（需清空代理变量，见下） |
| 类型检查 | `uv run pyright` | 0 errors |
| Lint / 格式 | `uv run ruff check` / `format --check` | 通过 |
| Web 单测 | `pnpm test:unit --run` | **59 passed** |
| Web 类型 / 构建 | `pnpm type-check` / `pnpm build` | 通过 |
| 打包 | `uv build` | `xiaoqiao-0.1.0-py3-none-any.whl` |
| CI | `.github/workflows/ci.yml` | **GitHub Actions 双 job 全绿**（run [39058498974](https://github.com/me9rez/xiaoqiao/actions/runs/39058498974)：python = lint + format + pyright + pytest，web = type-check + vitest + build，均在 ubuntu-latest 上） |

> 环境注意：宿主机 `NO_PROXY` 含裸 IPv6 `[::1]` 时，`httpx2` 解析代理会抛 `InvalidURL`，导致 `test_settings.py` 的一个用例失败。这是环境既有问题（升级前后一致），清空代理变量后 192 项全通过。CI 的 runner 无此变量，因此不受影响。

---

## 桌面化（2026-10-18，M0–M4）

方案见 [desktop-plan.md](desktop-plan.md)。M0 冒烟、M1 外壳、M2 稳定性、M3 原生集成已完成：

| 项 | 状态 |
|---|---|
| M0 可行性 | ✅ `file://` 加载、`file://`→`ws://127.0.0.1` 直连、`localStorage`、`randomUUID`/`subtle`、ES module 导入全部通过 |
| M1 引擎契约 | ✅ `--desktop`、`--ws-port 0`、`--auth-token`、`--exit-on-stdin-eof`、`shutdown` RPC |
| M1 前端 | ✅ 端点解析、握手排队、`auth_failed`、`vite --mode desktop` 相对 base、字体本地化 |
| M1 外壳 | ✅ `desktop/`（tinyjs.json + engine 守护 + api 面） |
| M2 稳定性 | ✅ 启动画面与错误横幅（重试/日志/打开目录）、崩溃退避重启、`engine.log`、单实例、托盘 + 关窗隐藏 |
| M2 R8 | ✅ `runtime/instance_lock.py`：回环 8760 端口当后台工作槽，抢不到即 passive（第二个引擎实测不启动调度器） |
| M3 原生集成 | ✅ 应用菜单（探针实测三个 id 就位）、焦点时的审批/完成通知、拖放路径进输入框、文件夹选择器、系统主题同步 |
| M4 独立运行时 | ✅ python-build-standalone 装在 
esources/python，wheel 装进它自己的 site-packages；打包版引擎来自它（不再依赖本机 uv），冷启动 2.3 s |
| 回归 | ✅ pytest **205**、vitest **84**、ruff/pyright 干净、type-check 与两种 vite 构建通过 |
| 打包冒烟 | ✅ `tinyjs build` → `desktop/dist/xiaoqiao.exe` 能拉起引擎并完成鉴权；杀外壳后引擎退出、端口释放 |

未做（按方案排期）：安装包与自更新 manifest、去端口化（M5）、中文输入法人工验收。

---

## 配置格式迁移（2026-10-18，config.toml）

方案见 [config-toml-plan.md](config-toml-plan.md)。运行配置由 `~/.xiaoqiao/settings.json` 改为
`~/.xiaoqiao/config.toml`（结构对齐 Kimi Code CLI），MCP server 定义拆到 `mcp.json`。

| 项 | 状态 |
|---|---|
| 结构 | ✅ `default_model` + `[providers.*]` + `[models."<alias>"]` + `[thinking]` + `[loop_control]` + `[limits]` + `[[permission.rules]]` + `[services.web_search]` |
| 读 | ✅ stdlib `tomllib`；逐字段容错（类型错只回落该字段并告警） |
| 写 | ✅ `tomlkit` 增量改写：只改动变化的键，注释/顺序/未知节保留，`os.replace` 原子替换 |
| 迁移 | ✅ 七类历史输入（provider/model、snake_case、`selectedModel`、最老扁平版、`mcpServers`、`webSearch`、无配置）；迁移后**保留** `settings.json` |
| 数据目录 | ✅ `XIAOQIAO_HOME` 覆盖；路径改为惰性求值（原先在 import 期冻结，测试只能 patch 模块变量） |
| RPC | ✅ `getSettings`/`updateSettings` 改 snake_case（与文件同一套词汇），旧 camelCase 入参保留兼容 shim |
| MCP | ✅ 定义移到 `mcp.json`，`type` 改为字段存在性判别（`command` / `url` / `transport = "sse"`），旧 `type` 仍可读 |
| 顺带修复 | ✅ 删除无消费者的 `workflowLoop`；`coding_tools._web_search` 不再自读 JSON，改走 `[services.web_search]`；`gateway/server.py` 的 effort 取值不再恒为空串 |
| 回归 | ✅ pytest **247**、vitest **84**、ruff/pyright 干净、`pnpm type-check` 与两种 vite 构建通过 |
| CLI | ✅ `xiaoqiao config path`（打印 config.toml/mcp.json 真实路径）与 `xiaoqiao config show`（输出解析后的值，api_key 打码） |
| 端到端 | ✅ 起真实网关连 WS：旧 `settings.json` 自动迁移 → `getSettings` 返回新词汇 → `updateSettings` 只改 `default_model` 一行 → 文件其余内容与注释不变 |


---

## 工作台体验（2026-10-18，M1–M5）

方案见 [workbench-plan.md](workbench-plan.md)（对标缺口来自 [grok-bot-comparison.md](grok-bot-comparison.md)）。

| 项 | 状态 |
|---|---|
| 状态可见性 | ✅ 服务端 `getActivity` 聚合 + `activity` 广播（四态：等你 / 在忙 / 出错 / 空闲）；`BotStatusDot` 三态点，`title` + `aria-label` 成套；刷新与多标签页一致 |
| 第一屏 | ✅ `chat-home` 改为 Now 视图：等你 / 需要看一眼 / 在忙 / 刚完成，无活动时回落到原输入框空状态 |
| 教一遍 | ✅ run 期间捕获工具调用序列（`run_steps` 表）→ `draftRoutineFromRun` 生成草稿 → Now 视图「存为定时任务」→ 步骤随 routine 落库并在触发时渲染进 prompt |
| 去重 | ✅ `/automation/tasks` 重定向到 `/routines`（此前两个入口同名「定时任务」，一 JSON 一 SQLite） |
| 顺带修复 | ✅ 无 group 目标的 routine 此前只打日志不执行，现投递到 Bot 自己的会话 |
| 回归 | ✅ pytest **266**、vitest **84**、pyright 0、ruff 干净、`pnpm type-check` 与 `pnpm build` 通过 |

未做：步骤清单的独立编辑 UI、会话页内的「存为定时任务」入口、事件监听的存储合并（仍走 JSON）。

## 设置页对齐 config.toml（2026-10-18）

方案与实施记录见 [config-toml-plan.md](config-toml-plan.md) §15。

| 项 | 状态 |
|---|---|
| AI 服务 | ✅ `/settings/models` 可增删 provider，编辑 `type` / `base_url` / `api_key`（打码可切换）/ `api_key_env`（此前「添加 AI 服务」按钮无 handler） |
| 模型 | ✅ 每个 alias 可展开编辑 `model` / `display_name` / `max_context_size` / `max_output_size` / `capabilities` / `support_efforts` / `default_effort`，可增删；改模型 id 时别名与 `default_model` 同步跟随 |
| 其余字段 | ✅ `default_model`、`[loop_control]` 三项、`[thinking]`、`[services.web_search]` 均可编辑；每个控件旁标出它在文件里的键 |
| 可见性 | ✅ 顶部横幅直说「没有可用 API key，回复来自假客户端」；每张卡片显示密钥来源（文件 / 环境变量 / 未找到） |
| 测试连接 | ✅ 新 RPC `testProvider`：`GET {base_url}/models`，不消耗 token，失败原因原文回显 |
| 安全 | ✅ `apply_update` 不再静默丢弃解析失败的模型（改为报错拒存）；新表头自动与上一节空行分隔 |
| 回归 | ✅ pytest **281**、vitest **92**、pyright 0、ruff 干净、`pnpm type-check` 通过；含一次真实网关 + Chromium 的增删 provider 落盘往返 |

未做：`api_key` 仍以明文经本机 WS 传给页面（要遮罩需引入 `has_api_key` + 「留空不改」语义）；图片生成无后端工具，页面上明确标注不提供配置。

## 模型选择交互（2026-10-18）

交互参考 Kimi Code CLI 的模型选择器，规范记入 [design.md](design.md) §14。

| 项 | 状态 |
|---|---|
| 胶囊 | ✅ 输入框右下显示「显示名 · 档位」，档位用强调色；模型为空时不渲染 |
| 浮层 | ✅ provider 名 → 该 provider 的模型（当前项打勾）→ 思考档位（默认 / High / Max）→ 缓存提示 → 更多模型…；此前只有一个下拉，没有 provider 分组与档位 |
| 对话框 | ✅ 「切换模型」：搜索（匹配名字 / 模型 id / 别名 / provider / 能力）、provider 筛选 chip、`deepseek · 128k ctx · 思考 · 工具调用` 副标题、收藏星、↑↓ / Enter / Esc |
| 数据源 | ✅ 两个视图共用一个 `useSettingsStore`，删掉 ChatInput 与 EmptyState 各自 `getSettings` 的副本；`utils/models.ts` 统一名字、档位与副标题 |
| 落点 | ✅ 选模型写 `default_model`（会话内另写 `session.model`）；思考档位写 `[thinking] effort`，「默认」即清空该键 |
| 顺带修复 | ✅ 点浮层内元素原先在 `mousedown` 阶段被判为「点外部」而先卸载，导致点模型 / 更多模型无反应（Teleport 到 `body` 后 `rootRef.contains` 不再成立） |
| 回归 | ✅ vitest **102**、type-check 与 `pnpm build` 通过；真实网关 + Chromium 走完「改模型 → 落盘 → 改回」「选 High → 落盘 → 点默认清空」两次往返 |

未做：思考档位是 `config.toml` 的全局 `[thinking] effort`（与设置页同一字段），不是按会话存储——参考实现是每会话值，需要新表 + 运行时读取路径才能对齐。

未做（方案 §12 明示）：Kimi 的 `managed:` 供应商 / OAuth / `secondary_model` / `hooks` / `background` /
`database` / `watch` / `tui.toml` / 项目级 `local.toml`；`anthropic` 客户端分派留作后续。

## 向 DeepSeek Bot 对齐（2026-10-18，M1）

方案与逐项对照见 [dsbot-alignment.md](dsbot-alignment.md)（参考 <https://github.com/Fei2411/DeepSeek-Bot>）。

| 项 | 状态 |
|---|---|
| 侧栏 | ✅ 单栏接管原有 64px Bot 轨道：品牌行（搜索 / 新建 / `⋯`）+ 主 Bot 卡片 + 群与 Bot 同列（emoji、名字、一句话副标题、状态点）+ 可折叠最近对话 + 底部「已连接引擎 · 设置」 |
| 顶部 | ✅ 通栏标题改为居中悬浮胶囊（emoji/成员堆叠 + 名字 + 状态点，非首页多一个 `←`） |
| 导航 | ✅ 工具箱 / 定时任务 / 运行记录 / 审批 从顶级项收进 `⋯` 菜单（路由不变） |
| 顺带修复 | ✅ 删除 `BotRail.vue`——它的 `handleSelect` 引用了未导入的 `sessionsStore`，点第二个 Bot 会抛 ReferenceError |
| type-check | ✅ `pnpm type-check` 由 `vue-tsc --noEmit`（根 tsconfig 只有 references，**实际什么都没检查**）改为 `vue-tsc --build`；随之暴露并修掉 8 个真实类型错误 |
| 回归 | ✅ `vue-tsc --build` 0 错误、vitest **102**、`pnpm build-only` 通过、Chromium 截图核对 |

后续里程碑（M2 消息流 / M3 bot 详情抽屉 / M4 设置与用量 / M5 后端补齐 / M6 能力与交接）见方案 §4。


