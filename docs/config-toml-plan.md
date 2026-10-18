# 技术方案：settings.json → config.toml（对齐 Kimi Code）

> 状态：待评审 · 2026-10-18 · 基线 `0c960e6`
> 调研对象：[Kimi Code CLI 配置文件](https://www.kimi.com/code/docs/kimi-code-cli/configuration/config-files.html)、[配置覆盖](https://www.kimi.com/code/docs/kimi-code-cli/configuration/overrides.html)、[MCP](https://www.kimi.com/code/docs/kimi-code-cli/customization/mcp.html)（2026-10 抓取）
> 配套：[desktop-plan.md](desktop-plan.md)、[status.md](status.md)、[protocol.md](protocol.md)

---

## 0. 结论

**做，一次性换到底，不留 JSON 双写并行期。**

理由不是「TOML 更时髦」，是三条实际收益：

1. **配置文件可以写注释了。** 现在 `settings.json` 由 `save()` 整份覆盖，用户手写的注释、空行、键顺序在一次 UI 保存后全部消失；`SettingsModelsView.vue` 在切换模型时（`watch primaryModel → saveSettings`）就会触发保存。TOML 配上保留格式的写入器，才谈得上「人可编辑的配置」。
2. **模型从「provider 内嵌数组」变成「扁平别名表」是真正的结构改善。** 现在模型是三级嵌套 `providers.<p>.models[].id`，取值路径散落在 web 的 `modelOptions`、Python 的 `model_config()`、界面里的 `${providerId}/${model.id}` 拼接三处。Kimi 的 `[models."<alias>"]` 把「别名」升为一等公民，与 session/bot 表里已经存着的 `"deepseek/deepseek-v4-flash"` 字符串**天然同构**，因此**不涉及任何数据库迁移**。
3. **顺手清掉三处历史债**（见 §2.3）：`workflow_loop` 死字段、`coding_tools.py` 绕过 Settings 直接读 JSON、`gateway/server.py:270` 恒取空串的 thinking 取值。

**关键决策**（细化见 §8，需评审确认）：

| 项 | 选择 |
|---|---|
| 文件位置 | `~/.xiaoqiao/config.toml`，新增 `XIAOQIAO_HOME` 覆盖；MCP server 定义拆到 `mcp.json` |
| 解析 / 写入 | 读 `tomllib`（stdlib），写 `tomlkit`（保留注释与格式）+ 原子替换 |
| 词汇 | 磁盘与 RPC 统一 snake_case，**只留一套** |
| 旧文件 | 迁移后 **保留 `settings.json` 原样**，不删不重命名 |

工作量约 **5–7 人日**（含 web 与测试），不动 agent 运行时语义，不动网关协议形状（只改字段词汇）。

不做：Kimi 的 `managed:` 供应商、OAuth、`secondary_model`、`hooks`、`background`、`database`、`watch`、`tui.toml`、项目级 `local.toml`——见 §12。

---

## 1. Kimi config.toml 调研结论

### 1.1 文件与命名

- 路径固定 `~/.kimi-code/config.toml`（或 `$KIMI_CODE_HOME/config.toml`），**首次运行自动创建**；终端界面偏好另存 `tui.toml`；项目级设置另存 `<项目>/.kimi-code/local.toml`。
- 字段名一律 **snake_case**；键里含 `.` 必须加引号（`[models."gpt-4.1"]`），否则 `.` 被解释成表分隔符。
- 结构只有两类：**顶层标量**（`default_model`、`telemetry` …）+ **嵌套表**（`providers`/`models`/`thinking`/`loop_control`/`permission` …）。

### 1.2 与我们相关的六张表

| 表 | 关键字段 | 语义要点 |
|---|---|---|
| `providers.<name>` | `type`（必填：`kimi`/`anthropic`/`openai`/`openai_responses`/`google-genai`/`vertexai`）、`api_key`、`api_key_env`、`base_url`、`oauth`、`env`、`custom_headers` | 凭证**只从配置文件读**，`export` 环境变量不生效；`api_key` 与 `api_key_env` 互斥；`api_key_env` 是唯一「显式从 shell 环境读」的通道 |
| `models.<alias>` | `provider`、`model`、`max_context_size`（必填）、`max_input_size`、`max_output_size`、`capabilities[]`、`support_efforts[]`、`default_effort`、`display_name`、`reasoning_key`、`adaptive_thinking`，另有 `.overrides` 子表 | 别名由 `default_model` / `-m` 引用；`capabilities` 只加不减；`default_effort` 必须属于 `support_efforts` |
| `[thinking]` | `enabled`（默认 true）、`effort`、`keep` | **main agent 上全局 `effort` 压过模型的 `default_effort`**；`enabled=false` 强制关 |
| `[loop_control]` | `max_steps_per_turn`、`max_attempts_per_step`、`reserved_context_size`、`compaction_max_attempts` | `max_steps_per_turn` 不设或 0 = 无上限 |
| `[permission]` | `dangerous_command_guard` + `[[permission.rules]]`（`decision`：`allow`/`deny`/`ask`；`scope`；`pattern`：`Read` 或 `Bash(rm -rf*)`；`reason`） | **按顺序匹配，第一条命中即生效**（因此书写顺序是语义的一部分） |
| `[services.<name>]` | 只认 `moonshot_search` / `moonshot_fetch`；字段 `base_url`、`api_key`、`oauth`、`custom_headers` | 其他 key 被忽略 |
| `[mcp]` | `startup_timeout_ms`、`tool_timeout_ms`、`default_deferred` | **MCP server 定义不在 `config.toml`**，写在 `mcp.json`（`{"mcpServers": {...}}`） |

### 1.3 优先级与失败策略

- 普通运行参数：**命令行 > 用户配置文件**；环境变量不是通用后备源（只有标注过的几个字段例外）。
- 供应商凭证解析链：`api_key` / `api_key_env`（互斥）> `[providers.<n>.env]` 子表 > 全缺则**启动报错**。
- 配置错误**直接报错，不静默回退**（至少对 `secondary_model` 明确如此）。

### 1.4 `mcp.json` 的形状（与我们的现状差异）

```json
{
  "mcpServers": {
    "filesystem": { "command": "npx", "args": ["-y", "...", "/tmp"] },
    "linear": { "url": "https://mcp.linear.app/mcp" },
    "legacy": { "transport": "sse", "url": "https://…/sse" }
  }
}
```

判别规则：有 `command` → stdio；有 `url` 且无 `transport` → HTTP；`transport = "sse"` → SSE。可选字段 `env`/`cwd`/`headers`/`bearerTokenEnvVar`/`enabled`/`deferred`/`startupTimeoutMs`/`toolTimeoutMs`/`enabledTools`/`disabledTools`。
**我们用 `type: "stdio"` 显式标注，而 Kimi 用字段存在性判别**——拆分时要翻译，并保留旧 `type` 键的读兼容。

---

## 2. 现状盘点

### 2.1 当前 `settings.json` 的真身

`python/src/xiaoqiao/settings.py` 的 `Settings` 有 9 个字段，但磁盘上的键比 dataclass 多——有一个字段**根本没进 dataclass**：

```
primaryModel              str              → default_model
providers.<id>.api        "openai-completions"
providers.<id>.baseUrl
providers.<id>.apiKey
providers.<id>.enabled    bool             （仅 web 读，Python 无人读）
providers.<id>.models[]   {id,name,contextWindow,maxTokens,reasoning,thinking_level[],input[]}
max_turns                 int
dailyTokenBudget / dailyBudgetUsd / maxRequestsPerMinute
mcpServers{}              <name>: {type, command, args[], …}
workflowLoop              bool             （死字段，见 2.3）
toolApproval{enabled, always_require[], never_require[]}
webSearch{provider, baseUrl, apiKey}       ← 不在 Settings 里，被 coding_tools 直接读文件
```

`load()` 目前兼容 4 种形状：新 provider/model、`primary_model` 下划线版、`selectedModel`/`selected_model` 旧版、以及「无 providers 但有 `model`/`base_url`/`api_key`」的最老版。这段兼容逻辑是本次迁移的**输入**，不是负担——它正好定义了迁移矩阵（§6.1）。

### 2.2 五个读写点（这是改造的真实边界）

| # | 位置 | 做什么 | 备注 |
|---|---|---|---|
| 1 | `settings.py` | `load()` / `save()` 全权拥有文件 | `_SETTINGS_PATH` 在**模块导入时**求值，测试只能 monkeypatch 模块变量 |
| 2 | `gateway/ws_server.py` | `getSettings`/`updateSettings` RPC（camelCase）；读预算、读 `tool_approval`、取 `thinking_level` | 见 500–536、709、1250、1271、1385、1399、1650、1678 |
| 3 | `mcp.py` | `install_connector` / `uninstall_connector` / `update_connector_config`：`load → 改 mcp_servers → save` | 连接器增删直接改写配置文件 |
| 4 | `tools/coding_tools.py` | `_web_search()` **自己打开 settings.json** 读 `webSearch` | 绕过 `Settings`，schema 完全不受控；错误信息还教用户去编辑 json |
| 5 | `runtime/backup.py` | `_EXTRA_FILES = ("settings.json",)` | 备份/恢复清单 |

### 2.3 三个必须先承认的历史债

1. **`workflow_loop` 是死字段。** `loop.py` / `workflow_loop.py` 在 harness 迁移时已删除（见 [agent-refactor-proposal.md](agent-refactor-proposal.md)），全仓只剩 `settings.py` 自己读写它。→ 新格式**不迁**，直接丢弃。
2. **`coding_tools.py` 直读 JSON。** `webSearch` 从没进过 `Settings`，意味着它不参与任何默认值、校验、备份语义（备份倒是备了整份文件）。→ 收进 `[services.web_search]`，由 `settings.services` 提供。
3. **`gateway/server.py:270`** 写的是 `getattr(self._settings, "thinking_level", "")`——`Settings` 上不存在这个属性（`thinking_level` 是函数），**恒为空串**。→ 换成 `settings.effective_effort(...)`，顺手修掉。

### 2.4 `providers.<id>.enabled` 与 `workflowLoop` 的共同病

两者都是「加了字段忘了接消费者」：`enabled` 只影响设置页的计数文案与卡片透明度，Python 侧零引用。新格式是清理这类字段的最后时机。

---

## 3. 目标格式

### 3.1 小巧的 `config.toml` 完整样例

```toml
# 小巧（Xiaoqiao）运行配置。字段命名与结构对齐 Kimi Code CLI 的 config.toml。
# 手工编辑安全：保存设置时只改写变化的键，注释与顺序保持不变。

default_model = "deepseek/deepseek-v4-flash"

[providers.deepseek]
type = "openai"                                # openai | anthropic | openai_responses
base_url = "https://api.deepseek.com/v1"
api_key = ""                                   # 明文密钥；留空则走 api_key_env
api_key_env = "DEEPSEEK_API_KEY"               # 从该环境变量取密钥（与 api_key 互斥）

[models."deepseek/deepseek-v4-flash"]
provider = "deepseek"
model = "deepseek-v4-flash"
max_context_size = 128000
max_output_size = 8000
capabilities = ["thinking", "tool_use"]
support_efforts = ["high", "max"]
default_effort = "max"
display_name = "DeepSeek V4 Flash"

[models."deepseek/deepseek-v4"]
provider = "deepseek"
model = "deepseek-v4"
max_context_size = 128000
max_output_size = 8000
capabilities = ["thinking", "tool_use"]
support_efforts = ["high", "max"]
default_effort = "max"
display_name = "DeepSeek V4"

[thinking]
enabled = true
# effort 留空：由各模型的 default_effort 决定（设了它就会覆盖所有模型）

[loop_control]
max_steps_per_turn = 25

[limits]                                        # 小巧扩展：Kimi 无对应表
daily_token_budget = 0                          # 0 = 不限
daily_budget_usd = 0.0
max_requests_per_minute = 0

[services.web_search]                           # 小巧扩展，形状对齐 [services.*]
provider = "bing"                               # bing | searxng
base_url = ""
api_key = ""

[[permission.rules]]
decision = "allow"                              # allow 必须写在 ask 之前，见 §4.3
pattern = "list_files"

[[permission.rules]]
decision = "ask"
pattern = "run_command"

[[permission.rules]]
decision = "ask"
pattern = "write_file"

[[permission.rules]]
decision = "ask"
pattern = "edit_file"

[[permission.rules]]
decision = "ask"
pattern = "http_fetch"
```

MCP server 定义在同目录 `mcp.json`：

```json
{
  "mcpServers": {
    "fetch": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-fetch"] }
  }
}
```

### 3.2 字段映射表

「现在」→「新格式」，**每一行都要有处理方式**，没有「以后再说」：

| 现在 | 新格式 | 处理 |
|---|---|---|
| `primaryModel` / `primary_model` / `selectedModel` / `selected_model` | `default_model` | 值不变，仍是 `<provider>/<model>` |
| `providers.<id>.api` = `openai-completions` | `[providers.<id>] type` | 值映射：`openai-completions`/`openai` → `openai`；`anthropic*` → `anthropic`；未知 → `openai` + 警告 |
| `providers.<id>.baseUrl` | `base_url` | 原样 |
| `providers.<id>.apiKey` | `api_key` + `api_key_env` | 有 key 写 `api_key`；deepseek/openai 默认补 `api_key_env`（保持今天「没配 key 也能跑」的路径，见 §4.5） |
| `providers.<id>.enabled` | **删除** | Python 零引用（§2.4）；见决策 D2 |
| `providers.<id>.models[]` | `[models."<provider>/<id>"]` | 扁平化，key = 别名 |
| `…models[].id` | `models.<alias>.model` | 线上模型名 |
| `…models[].name` | `display_name` | 缺省回退 `model` |
| `…models[].contextWindow` | `max_context_size` | 缺省 128000（与今天默认一致） |
| `…models[].maxTokens` | `max_output_size` | 缺省 8000。**注意**：Kimi 只在 anthropic 读它，我们真的要它——harness 压缩需要 `max_context_window_tokens` 与 `max_output_tokens` **同时**存在（`agent_runtime.py:257-277`） |
| `…models[].reasoning` | `capabilities` 含 `thinking` | 布尔并入能力标签 |
| `…models[].thinking_level[]` | `support_efforts` + `default_effort = levels[-1]` | 保住今天「最后一档为默认」的语义（`settings.thinking_level()` 取 `[-1]`） |
| `…models[].input[]` | `capabilities` 里的 `image_in`/`video_in`/`audio_in` | `text` 隐含，不写 |
| `max_turns` | `[loop_control] max_steps_per_turn` | 语义一致：单轮工具调用步数上限（`build_client` 的 `max_iterations`） |
| `dailyTokenBudget` | `[limits] daily_token_budget` | 0 = 不限 |
| `dailyBudgetUsd` | `[limits] daily_budget_usd` | float，0.0 = 不限 |
| `maxRequestsPerMinute` | `[limits] max_requests_per_minute` | 0 = 不限 |
| `toolApproval.enabled` | `default_permission_mode` | `true` → `manual`；`false` → `yolo` |
| `toolApproval.always_require[]` | `[[permission.rules]] decision="ask"` | 顺序见 §4.3 |
| `toolApproval.never_require[]` | `[[permission.rules]] decision="allow"` | 必须排在 ask 之前 |
| `mcpServers` | `mcp.json` 的 `mcpServers` | `type:"stdio"` → 只留 `command`；`sse`/`http` → `url` + `transport` |
| `workflowLoop` | **删除** | 死字段（§2.3） |
| `webSearch{provider,baseUrl,apiKey}` | `[services.web_search]` | 新进 `Settings.services`，不再直读文件 |

---

## 4. 语义规则（必须写进实现，不能靠约定）

### 4.1 别名解析

```
alias → 优先 models[alias] 精确命中
      → 未命中则按第一个 "/" 拆成 (provider, model)，在 models 里找 provider+model 匹配者
      → 仍未命中 → 报错（日志 + RPC error），不回落到别的模型
```

第二条是为了兼容两类存量数据：`sessions`/`bots` 表里存的模型串（今天就是 `provider/model`，迁移后正好是别名，**通常第一条就命中**），以及用户 `-m deepseek/deepseek-v4` 手输。**注意别名本身可能含多个 `/`**（如 `openrouter/anthropic/claude`），所以必须「先精确查表，再拆」。

### 4.2 thinking 解析

```
if not thinking.enabled:            → 不发 thinking 参数
elif "thinking" not in capabilities and not support_efforts:
                                    → 不发（非推理模型）
else: effort = thinking.effort or models[alias].default_effort
```

默认配置**不写** `[thinking].effort`，于是每模型 `default_effort` 生效——与今天「按模型取最后一档」等价。写全局 `effort` 是给用户「一刀切」用的（这与 Kimi 的覆盖方向一致：全局大于模型）。

### 4.3 权限规则：顺序即语义

今天的判定顺序（`coding_tools.py:64-69`）是 **`never_require` 先于 `always_require`**，即 allow 优先。Kimi 是「数组首条命中」。

两者要同时满足，唯一办法是**写盘时把 allow 规则排在 ask 规则前面**，并在文档与注释里写死这条约束。代码侧的 `PermissionSettings` 保留三个集合（`deny`/`allow`/`ask`），判定顺序固定 `deny > allow > ask`；序列化时才把顺序落成文本。

用户手改文件若打乱顺序，TOML 语义（首条命中）会与代码语义（固定优先级）不一致——**以文件顺序为准**（即用户意图优先），代码只负责「按顺序逐条匹配」。这样两边永远一致，代价是迁移写出的顺序必须正确。

### 4.4 预算

`0` = 不限，与现状一致（`ws_server.py:1385/1399-1403`）。

### 4.5 凭证

```
api_key 非空           → 用它
elif api_key_env 有值  → 从该环境变量取（每次请求重读）
elif providers.<id>.env 子表 → 读（Kimi 兼容位，我们默认不生成）
else                   → 退回 DEEPSEEK_API_KEY / OPENAI_API_KEY（一次性弃用警告）
全无                   → _FakeClient（保持 demo/CI 路径，见决策 D3）
```

与 Kimi 的**有意偏离**：Kimi 在「凭证全缺」时启动即失败，我们保留 `_FakeClient`——因为 `test_settings.py` 与若干本地开发路径依赖「没 key 也能起网关」。这条要在文档里标成 deviation，而不是装作一致。

---

## 5. 读写实现

### 5.1 模块切分（避免一次性改 35 个 import）

```
xiaoqiao/config/__init__.py    # 对外门面：load/save/config_path/load_mcp/…
xiaoqiao/config/schema.py      # dataclass：Settings/ProviderSettings/ModelSettings/…
xiaoqiao/config/reader.py      # tomllib 解析 → Settings
xiaoqiao/config/writer.py      # tomlkit 增量写 + 原子替换
xiaoqiao/config/migrate.py     # settings.json（4 种形状）+ mcpServers → 新格式
xiaoqiao/settings.py           # 保留为薄门面，re-export 旧名字（load/save/build_client/…）
```

`settings.py` 作为门面保留，`main.py`/`mcp.py`/`ws_server.py` 的 `from xiaoqiao.settings import …` 全部不用改——改造风险从「35 个 import 点」压到「6 个模块」。

### 5.2 类型化模型

```python
@dataclass
class ProviderSettings:
    type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    api_key_env: str | None = None
    custom_headers: dict[str, str] = field(default_factory=dict)

@dataclass
class ModelSettings:
    provider: str
    model: str
    max_context_size: int = 128_000
    max_input_size: int | None = None
    max_output_size: int | None = None
    capabilities: list[str] = field(default_factory=list)
    support_efforts: list[str] = field(default_factory=list)
    default_effort: str | None = None
    display_name: str | None = None
```

**为什么值得换掉 dict**：现在是 `cfg.get("contextWindow")` 这种字符串取值，拼错一个字母就是静默 None（`agent_runtime.py:268` 的风格）。换成属性后 pyright 直接拦住——而 pyright 已在 CI 里跑。

代价：`test_agent_runtime.py:38`、`test_settings.py:48` 这类「拿 dict 直接改」的测试要改写成构造 dataclass。

### 5.3 写入：保留注释

```python
doc = tomlkit.parse(path.read_text(encoding="utf-8"))   # 失败 → §5.5
_sync(doc, settings)          # 只 set 已知键；值未变则一个字符都不动
tmp = path.with_suffix(".toml.tmp")
tmp.write_text(tomlkit.dumps(doc), encoding="utf-8")
os.replace(tmp, path)         # 原子替换，避免半截文件
```

`_sync` 的规则：
- **只写变化的键**：比较旧值，相等就跳过（这样切一次模型只改动 `default_model` 一行，diff 干净）。
- **未知键原样保留**：用户手写的、我们还不认识的节不会被抹掉。
- **空值处理**：`api_key = ""` 保留（Kimi 自己也这么写），可选的 `None` 值删除键而非写空。
- 整数/浮点类型要对：`daily_budget_usd` 必须写 `0.0`，写成 `0` 会让读取端拿到 int（虽然 `float()` 能兜住，但 diff 会抖）。

### 5.4 路径与 `XIAOQIAO_HOME`

- `paths.config_dir()` 首查 `XIAOQIAO_HOME`（对齐 `KIMI_CODE_HOME`），否则走现有的 `~/.xiaoqiao` → `~/.coding-agent` 兼容逻辑。
- **`settings.py:45` 的模块级 `_SETTINGS_PATH` 改成 `config_path()` 函数**。这是现在测试必须 monkeypatch 模块变量的根因；同时它会让 `XIAOQIAO_HOME` 在导入之后设置也生效。
- 新增 `xiaoqiao config path` / `xiaoqiao config show`（打印真实路径与解析后的值，`api_key` 打码）——用户排错时最想知道的两件事。

### 5.5 失败策略

| 情况 | 行为 |
|---|---|
| `config.toml` 不存在，`settings.json` 存在 | 迁移（§6） |
| 两者都不存在 | 写默认 `config.toml`（Kimi 也是首启创建） |
| `config.toml` 解析失败 | 原文另存 `config.toml.broken-<ts>`，用默认值继续，**日志 ERROR 级**并带上报错行号 |
| 字段类型错（如 `max_context_size = "128k"`） | 该字段回落默认 + 警告，**不整份报废**（与 Kimi「错误一律报错」有意不同，见 deviation 表） |
| 写入失败（只读目录/权限） | 捕获、日志、RPC 返回 error；不让保存异常冒泡导致网关崩 |

---

## 6. 迁移

### 6.1 输入矩阵

| 输入 | 处理 |
|---|---|
| A. 新 provider/model 布局（当前主流） | 逐字段映射（§3.2） |
| B. 下划线版（`primary_model` / `max_turns` 等） | 同上，读时先归一化键名 |
| C. `selectedModel` / `selected_model` 旧版 | 同上 |
| D. 最老版：无 `providers`，有 `model`/`base_url`/`api_key` | 现 `_infer_provider()` 逻辑复用：推断 provider 名 → 生成一条 provider + 一条 model |
| E. 含 `mcpServers` | 写入 `mcp.json`（`type` 翻译见 §1.4） |
| F. 含 `webSearch` | 写入 `[services.web_search]` |
| G. 完全无配置 | 写默认 `config.toml` |

### 6.2 步骤

1. `load()`：`config.toml` 存在 → 读它，结束（快路径，**不碰 settings.json**）。
2. 否则 `settings.json` 存在 → 旧解析（复用现有 `load()` 的四段兼容）→ 生成 `config.toml`（原子写）→ 生成/合并 `mcp.json` → **`settings.json` 原样保留**（不删、不重命名）→ 日志一条 INFO：`配置已迁移到 config.toml；settings.json 保留但不再读取`。
3. 迁移只做一次：第 2 步之后 `config.toml` 存在，第 1 步永远命中。

**为什么保留 `settings.json` 而不删**：降级兼容——已发布的 wheel（0.1.0）和已经在跑的老桌面版仍会读它，删掉等于把老版本的配置清空。代价是两份文件可能不同步，用日志 + `xiaoqiao config path` 显式告知；下个大版本再删。

### 6.3 回滚

代码 `git revert` + 删除 `config.toml` 即回到 JSON 路径（第 2 步只在 `config.toml` 不存在时触发）。`settings.json` 全程未被改写，因此回滚零数据损失。

---

## 7. 波及面清单

| 文件 | 改动 | 风险 |
|---|---|---|
| `python/src/xiaoqiao/config/*`（新） | schema / reader / writer / migrate | 中：新代码，测试覆盖要扎实 |
| `settings.py` | 瘦成门面；`build_client`/`resolve_api_key`/`model_config`/`thinking_level` 保留签名但内部走新模型；新增 `effective_effort()` | 中 |
| `paths.py` | `XIAOQIAO_HOME`；`config_path()` 惰性 | 低 |
| `gateway/ws_server.py` | `getSettings`/`updateSettings` 换 snake_case；预算/权限/effort 取值改新 API；兼容旧 camelCase 入参（shim） | 中 |
| `gateway/server.py` | 修 `thinking_level` 恒空；`tool_approval` 取值改新 API | 低（顺手修 bug） |
| `mcp.py` | 连接器 CRUD 改读写 `mcp.json`；`create_mcp_tools` 从 `mcp.json` 取 server | 中 |
| `tools/coding_tools.py` | `_web_search` 改读 `settings.services`；错误文案不再指向 json | 低 |
| `runtime/backup.py` | `_EXTRA_FILES = ("config.toml", "mcp.json", "settings.json")` | 低 |
| `agent_runtime.py` | `model_config()` 返回 dataclass，改属性访问 | 低（类型化后更安全） |
| `main.py` | docstring/help 文案；`--test` 路径的 effort 取值 | 低 |
| `web/src/types/session.ts` | Settings/ProviderConfig/ModelSettings 类型重写 | 中：type-check 会抓 |
| `web/src/stores/settings.ts` | `modelOptions` 改遍历扁平 `models`；defaultSettings 换新形状 | 中 |
| `web/src/views/settings/SettingsModelsView.vue` | 模型按 provider 过滤；删除 enable 开关（D2） | 中 |
| `web/src/components/chat/ChatInput.vue`、`EmptyState.vue` | `primaryModel` → `default_model` | 低 |
| `python/tests/unit/test_settings.py`、`test_agent_runtime.py`、`test_mcp.py`、`test_backup.py` | 适配 | 中 |
| `python/tests/unit/test_config_toml.py`（新） | 迁移矩阵 + round-trip + 注释保留 + 损坏回退 + 原子写 + env 覆盖 | — |
| `AGENTS.md`、`README(.zh).md`、`docs/status.md` | 配置段全部改写 | 低 |

---

## 8. 待评审决策

| # | 决策 | 推荐 | 备选与代价 |
|---|---|---|---|
| D1 | RPC 词汇 | **snake_case**，与磁盘一致 | 保留 camelCase：省掉 6 处前端改动，但从此永久维护两套词汇 |
| D2 | `providers.<id>.enabled` | **删除** | 保留为扩展键：Schema 多一个 Kimi 没有的字段，且 Python 依然不读 |
| D3 | 无 API key 时 | **仍走 `_FakeClient`** | 学 Kimi 启动即报错：更「正确」，但打断 demo 与既有测试路径 |
| D4 | 写入库 | **`tomlkit`** | `tomli-w`：少一个依赖，但保存即丢注释（切模型就会触发） |
| D5 | MCP server 存放 | **拆到 `mcp.json`** | 留在 `config.toml` 的 `[mcp_servers.*]`：少一个文件，但与 Kimi 结构性不一致，且 `[mcp]` 已被 Kimi 征用为超时表 |
| D6 | 扩展段名 | **`[limits]`** | `[budget]` / `[usage]` |

---

## 9. 里程碑

| 里程碑 | 内容 | 出口判据 | 人日 |
|---|---|---|---|
| M1 | schema + reader + 迁移器 + `XIAOQIAO_HOME` | `config.toml` 能读；7 类输入迁移矩阵全绿；旧 `settings.json` 用户升级后行为不变 | 1.5 |
| M2 | writer（tomlkit 增量 + 原子写 + 损坏回退） | 「切模型只改一行」「手写注释保留」「坏文件留档」三条测试通过 | 1 |
| M3 | 消费方收敛（ws_server / server / agent_runtime / coding_tools / backup） | pytest 全绿；`gateway/server.py` 的 effort 不再恒空 | 1 |
| M4 | MCP 拆分 `mcp.json` | 连接器增删改走新文件；旧 `mcpServers` 自动迁移 | 1 |
| M5 | web 与文档 | `pnpm type-check` + vitest 绿；设置页能切模型并只改一行文件；AGENTS/README/status 更新 | 1.5 |
| M6（可选） | `anthropic` 客户端分派（`type` 已就位） | — | 后续 |

---

## 10. 风险与对策

| # | 风险 | 对策 |
|---|---|---|
| R1 | 迁移覆盖用户配置 | 原子写 + 迁移前不删原文件 + `config.toml.broken-<ts>` 留档 |
| R2 | 注释/顺序被保存动作抹掉 | tomlkit 增量写；值未变不落盘；测试里断言「注释仍在」 |
| R3 | 两套词汇长期并存 | D1 一次定死；只保留一个「旧 camelCase 入参」兼容 shim，并在 M5 后标 TODO 删除 |
| R4 | 别名含 `.` 或 `/` 导致键解析歧义 | **所有别名键一律加引号**；解析「先精确查表再拆」 |
| R5 | 类型化改造引发大面积测试失败 | `settings.py` 保留门面签名，把改动面压到 6 个模块；先落 M1 再动消费方 |
| R6 | 老前端调用 `updateSettings {primaryModel}` | 入参归一化 shim（10 行），识别 `primaryModel`→`default_model` 等旧键 |
| R7 | 权限规则顺序被人手改坏 | 代码「按文件顺序匹配」，不做二次排序；文件头写注释说明 |
| R8 | 回归基线漂移（205 pytest / 84 vitest） | 每个里程碑跑全量；`docs/status.md` 数字同步更新 |

---

## 11. 验证计划

**自动化（新增 `tests/unit/test_config_toml.py`）**

1. 七类输入 → 迁移结果逐字段断言（A–G，§6.1）
2. 迁移幂等：跑两次结果一致
3. round-trip：`load → save → load` 深相等
4. 注释保留：手写注释的文件保存后注释仍在、未知键仍在
5. 只改变化：切 `default_model` 后文件 diff 只有一行
6. 损坏回退：非法 TOML → 留档 `broken-*` + 回落默认 + ERROR 日志
7. 原子写：写临时文件后 `os.replace`（可用 mock 校验顺序）
8. `XIAOQIAO_HOME` 覆盖优先级 > `~/.xiaoqiao` > `~/.coding-agent`
9. 别名解析：精确命中 / 拆分子串命中 / 未命中报错
10. 权限顺序：allow 在 ask 前 → allow 生效；顺序颠倒 → 以文件为准
11. effort 解析四分支（§4.2）
12. `api_key` vs `api_key_env` 互斥与回落

**手工验收**

- 用旧 `settings.json` 起网关 → `config.toml` 生成、模型/thinking 行为不变
- 设置页切模型 → 文件只变一行，手写注释还在
- 手改 `default_effort = "high"` → 下一轮请求的 reasoning_effort 跟着变
- 把 `config.toml` 写坏 → 网关仍能起（默认值），日志里有文件名与行号
- 桌面版（`desktop/dist/xiaoqiao.exe`）沿用同一份 `~/.xiaoqiao/config.toml`

---

## 12. 不做什么

| 不做 | 原因 |
|---|---|
| `managed:` 供应商 / OAuth / `[providers.x.oauth]` | 我们没有托管平台，没有登录流程 |
| `secondary_model` / subagent 模型池 | 我们没有 `Agent`/`AgentSwarm` 工具 |
| `hooks` | 无 hook 执行器；且与「工具审批」职责重叠 |
| `background` / `database` / `watch` / `read` / `image` | 对应的子系统我们或没有、或语义不同（例如我们的压缩由 harness 负责） |
| `tui.toml` / 项目级 `local.toml` | 我们没有 TUI；项目级配置是独立议题 |
| `telemetry` / `identity` / `default_plan_mode` | 无对应功能 |
| 删除 `settings.json` | 破坏降级兼容（§6.2） |

---

## 13. 偏离 Kimi 的地方（明示，不装作一致）

| 项 | Kimi | 小巧 | 理由 |
|---|---|---|---|
| 无凭证时 | 启动报错 | `_FakeClient` + 警告 | 保留 demo/CI 路径（D3） |
| 配置字段类型错误 | 直接报错 | 单字段回落默认 + 警告 | 一个手误不该让网关起不来 |
| `max_output_size` | 仅 anthropic 读 | 我们真的用它约束 harness 输出上限 | 压缩需要两个边界同时存在 |
| `[limits]` / `[services.web_search]` | 无 | 扩展段 | 日预算与搜索供应商是我们已有的功能 |

---

## 14. 实施记录（2026-10-18，M1–M5 完成）

### 14.1 落地文件

| 文件 | 内容 |
|---|---|
| `python/src/xiaoqiao/config/schema.py` | 类型化模型：`Settings` / `ProviderSettings` / `ModelSettings` / `ThinkingSettings` / `LoopControlSettings` / `LimitsSettings` / `PermissionSettings` / `ServiceSettings`；别名解析与 `effective_effort()` 也在这里 |
| `config/reader.py` | `tomllib` → `Settings`，逐字段容错 |
| `config/writer.py` | `tomlkit` 增量同步 + 原子替换；`_set()` 只在值变化时写入 |
| `config/migrate.py` | 旧 `settings.json`（4 种形状 + `webSearch`）→ `Settings` + `mcp_servers` |
| `settings.py` | 门面：`load/save/build_client/model_config/resolve_api_key/effective_effort/to_wire/apply_update` |
| `mcp_config.py` | `mcp.json` 读写与 `type` ↔ 存在性判别 |
| `paths.py` | `XIAOQIAO_HOME`、`config_path()`、`mcp_config_path()`、`legacy_settings_path()` |
| `tests/unit/test_config_toml.py` | 33 项：迁移矩阵、round-trip、注释保留、只改一行、不写不变、原子写、损坏留档、类型回落、别名解析、权限顺序、wire 格式 |

### 14.2 实施中与方案的偏差

1. **`Settings` 不再保留旧字段的兼容属性**（方案 §5.2 说「门面保留签名」）。实际做法是保留**模块级函数**（`load/save/build_client/model_config`），把**字段访问点**全部改成新 API。理由：`getattr(settings, "daily_token_budget", 0)` 这类写法正是 §2.3 里「加了字段忘了接消费者」的温床，留着旧属性等于把问题固化。
2. **`workflowLoop` 直接不迁移**，仅在迁移日志里记一条 INFO。方案说的是「删除」，实施确认全仓零消费者。
3. **权限规则在 `coding_tools.py` 里改用 `fnmatch` 匹配**，让 `mcp__github__*` 这类通配在旧的 `{always_require, never_require}` 投影里也能生效（方案只要求顺序一致，没提通配；这是实施时发现的必要补充）。
4. **`[services.web_search]` 多一个 `provider` 字段**（`bing`/`searxng`），因为我们的搜索是自选供应商，Kimi 的 `moonshot_search` 是托管服务。

### 14.3 验证证据

- `uv run pytest -q` → **247 passed**（迁移前 205；新增 33 项 config 测试 + 若干 settings/api-key/effort 用例）
- `uv run pyright` → 0 errors；`ruff check` / `ruff format --check` 干净
- `pnpm type-check` 通过；`pnpm test:unit --run` → **84 passed**；`pnpm build` 与 `vite build --mode desktop` 均通过
- **端到端**：用 `XIAOQIAO_HOME` 指向临时目录 + 一份旧 `settings.json` 起真实 `WsGatewayServer`，
  WS 客户端收到 ready → `getSettings` 返回 `default_model/providers/models/thinking/loop_control/limits/permission/services`
  → `updateSettings {default_model}` → 落盘文件只变 `default_model` 一行，注释与其余节不动 → `shutdown` 正常停止
- 手写注释 + 自定义 `[my_custom]` 节在保存后仍在（`test_comments_and_unknown_keys_survive_a_save`）

### 14.4 遗留

- `anthropic` 客户端分派（`type` 已就位，`build_client` 目前对非 `openai` 类型记一条 warning 后仍走 OpenAI 兼容客户端）。
- `settings.json` 计划在下个大版本删除。
