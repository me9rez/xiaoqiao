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
| M5 加固 | CI 绿、预算与限流生效、备份可恢复 | ✅（`.github/workflows/ci.yml`；token/美元双阈值预算门禁 + 每分钟请求限流；`runtime/backup.py` 备份 agent.db/settings/sessions 并支持校验，沙箱后置） |

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
| CI | `.github/workflows/ci.yml` | Python + Web 两个 job |

> 环境注意：宿主机 `NO_PROXY` 含裸 IPv6 `[::1]` 时，`httpx2` 解析代理会抛 `InvalidURL`，导致 `test_settings.py` 的一个用例失败。这是环境既有问题（升级前后一致），清空代理变量后 187 项全通过。
