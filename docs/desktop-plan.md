# 技术方案：用 tinyjs 把 web 前端变成桌面应用

> 状态：待评审 · 2026-10 · 基线：`9bdeb28`（CI 双 job 全绿之后）
> 配套：[product.md](product.md)（产品定位）、[pivot-plan.md](pivot-plan.md)（后端运行时方案）、[design.md](design.md)（前端设计规范）、[status.md](status.md)（实施审计）
> 调研对象：[tarwin/tinyjsapp](https://github.com/tarwin/tinyjsapp)（README + 配置 schema，2026-10 抓取）

---

## 0. 结论

**做。** 技术路径是：保持现有 Vue 前端与 Python 后端的 RPC 面不变，用 tinyjs 提供一个原生外壳窗口，由 tinyjs 的 JS 后端负责**拉起并守护 Python 进程**，页面通过本机回环 WebSocket 连过去。第一阶段约 6–8 人日可拿到一个能日常使用的 Windows 桌面版；去端口化（把 RPC 收进 tinyjs bridge）作为第二阶段。

三个关键判断：

1. **不用 tinyjs 的 `url` 包装模式**（`"url": "http://127.0.0.1:8766"`）。它能一天出活，但保留了一个 HTTP 服务、丢掉离线与单实例，属于演示路径。
2. **页面走本地静态文件（`file://`），不靠 HTTP 服务器**。这是 tinyjs 的设计前提，也是它 6 MB 的原因。
3. **Python 走 sidecar**（PyInstaller onefile），不重写运行时。tinyjs 的 `executables/` 正是为这种场景准备的。

我们已经具备的有利条件比预期多：路由已经是 hash 模式、CSS/JS 没有任何 WebKit 敏感特性（实测 0 命中）、前端与网关之间只有一个 `GatewayService` 类作为接缝。

---

## 1. tinyjs 调研结论

### 1.1 运行时模型

```
┌──────────────────────┐   socket/pipe   ┌──────────────────────────┐
│ backend (txiki.js)   │◄───────────────►│ launcher (C++, 1–2 MB)   │
│ src/backend/main.js  │  NDJSON 行协议   │ WKWebView / WebView2 /   │
│ · 系统能力(fs/net/   │                 │ WebKitGTK 窗口           │
│   spawn/FFI/sqlite)  │                 └──────────┬───────────────┘
└──────────┬───────────┘                            │
           │ spawn                                    │ file:// 加载
┌──────────▼───────────┐                 ┌──────────▼───────────────┐
│ 我们的 Python 引擎     │                 │ 我们的 Vue 页面           │
│ (sidecar, 无窗口)     │◄────────────────│ window.tiny / WebSocket  │
└──────────────────────┘   ws://127.0.0.1 └──────────────────────────┘
```

- **体积**：约 6 MB，两个可执行文件，不打包 Chromium、不打包 Node。
- **后端是 txiki.js**：V8 单文件运行时，具备 fs / net / spawn / FFI / SQLite，ES 模块。
- **前端是普通 HTML/CSS/JS**，由系统 WebView 渲染（Windows = WebView2，macOS = WKWebView，Linux = WebKitGTK 4.1）。
- **页面通过注入的 `window.tiny` 与后端通信**：`tiny.api.call(method, params)` 请求/响应，`tiny.api.on(event, fn)` 后端推送，无需自己写协议。
- **页面加载方式**：`file://` 真实文档（不是 `set_html`），所以多文件前端、相对路径资源都能用，并且是 secure context。
- **构建产物**：`tinyjs build` 出 `.app` / exe / 裸目录；`tinyjs publish` 出带 sha256 的更新包 + manifest；`tiny.app.update.check/install()` 应用内自更新。
- **对 Vite 项目有官方模板**：`tinyjs new myapp --template vue-ts`，配 `frontend.build / dist / dev / devUrl` 后，`tinyjs dev` 里跑 Vite HMR，`tinyjs build` 里直接吃构建产物。

### 1.2 与我们直接相关的能力

| 能力 | 对我们的用途 |
|---|---|
| `tjs.spawn` + 管道 stdout/stderr | 拉起 Python 引擎、解析启动就绪行、崩溃重启 |
| `app.paths()` | 拿到 userData / resources / executables 真实路径 |
| `executables/` | 把 PyInstaller 产物作为 sidecar 随包分发 |
| `tiny.notify` / `tray.set` / `badge` | 审批待办、长任务完成、后台常驻的可见性 |
| `menu.set` + `onMenu` | 原生菜单（新建会话 / 设置 / 打开日志 / 退出） |
| `dialog` 原生文件面板 | 工作目录选择器（现在只能手输路径） |
| 拖放 `DROP` 带真实路径 | 把文件拖进输入框当上下文 |
| `app.theme.get()` + `theme` 事件 | 与系统深浅色同步（替代现在的 matchMedia 猜测） |
| `app.secrets` | 以后把 API key 放进系统凭据库，不再明文存 settings.json |
| `update` + manifest | 桌面端自更新 |
| `tinyjs.json` 的 `api` 能力门 | 白名单化页面可调用的 bridge 方法 |

### 1.3 与我们冲突的约束（必须正面处理）

| 约束 | 影响 | 处置 |
|---|---|---|
| 页面是 `file://` 起源 | 绝对路径 `/assets/*` 全废；`base: '/'` 必然白屏 | Vite 桌面构建改 `base: './'`；`index.html` 里 `/icon.png` 改相对 |
| 无 HTTP 服务 | 现在 `--web` 同时提供静态站与 WS，桌面端只要 WS | 桌面模式不启静态服务（新增 `--desktop` 语义） |
| 系统 WebView ≠ Chromium | 语法/渲染差异有踩坑空间 | 已审计：`backdrop-filter`/`color-mix`/`:has(`/`@container` **0 命中**，`toSorted`/`Object.groupBy` **0 命中**，风险低；仍需 M0 实机过一遍 |
| 固定的 8765 端口 | 多实例冲突、被别的进程占用；`_free_port()` 会**杀掉占用者**（危险） | 桌面端用 `--ws-port 0` 拿临时端口；**桌面模式必须禁用 `_free_port`** |
| 没有 `window.tiny` 的降级路径 | 浏览器 `--web` 模式仍要能用 | 传输层抽象，两套实现 |
| 外链字体（`cdn.jsdelivr.net`） | 断网即掉字体，桌面应用不能这样 | 字体改 npm 依赖本地打包 |

---

## 2. 现状审计（代码事实）

### 2.1 前端

| 位置 | 现状 | 对桌面化的影响 |
|---|---|---|
| `web/src/router/index.ts:8` | **已经是 `createWebHashHistory()`** | ✅ `file://` 下路由直接可用，无需改动 |
| `web/src/services/gateway.ts:5` | `DEFAULT_WS_URL = 'ws://127.0.0.1:8765'` 硬编码；`GatewayService` 内部 `new WebSocket(this.url)` | 需要「先拿到端点再连接」的启动时序 |
| `web/src/services/gateway.ts:186` | `export const gatewayService = new GatewayService()` 单例 | 保持导出名不变，store 层零改动 |
| `web/src/main.ts:30` | `gatewayService.connect()` 同步调用 | 改异步 bootstrap（等外壳给出端点） |
| `web/vite.config.ts` | 未设 `base` → 默认 `/` | 桌面构建必须 `./` |
| `web/index.html:39-41` | `<link rel="preconnect" href="https://cdn.jsdelivr.net">` + 两个字体 CSS | 离线/桌面必须本地化 |
| `web/index.html:5` | `<link rel="icon" href="/icon.png">` | 绝对路径，`file://` 下失效 |
| `web/src/theme.ts` | localStorage + `matchMedia` 推断深浅色 | 桌面端应改为读 `tiny.app.theme` 并订阅变化 |
| 全量 CSS/TS 审计 | `backdrop-filter`、`color-mix`、`:has(`、`@container`、`subgrid`、`toSorted`、`Object.groupBy`、`structuredClone` 命中数 **0** | ✅ WebKit 兼容风险显著低于一般 Vue 项目 |

### 2.2 后端

| 位置 | 现状 | 影响 |
|---|---|---|
| `python/src/xiaoqiao/gateway/ws_server.py:1830` | `async with serve(self._handle_ws, self._host, self._port)`，随后打印**固定**端口 | 需要 `--ws-port 0` + 打印**实际**端口 |
| `python/src/xiaoqiao/gateway/ws_server.py:330,341` | `_broadcast` / `_send_rpc_response` 直接调 `self._ws.send(...)`、遍历 `_connections` 的 send | 第二阶段去端口化的改造面（约 5 个方法） |
| `python/src/xiaoqiao/gateway/ws_server.py` 全文 | **无鉴权、无 Origin 校验**，握手即信任 | 本机任意进程可连；桌面版应加 token 握手 |
| `python/src/xiaoqiao/main.py:64-96` | `_free_port()` 在 Windows 上 `Stop-Process` 掉占用 8765/8766 的进程 | 桌面模式必须跳过，否则可能误杀用户的其他程序 |
| `python/src/xiaoqiao/main.py:294-313` | `--web` = 静态服务器（线程）+ WS | 桌面端只要 WS，静态服务由 tinyjs 从 `file://` 提供 |
| `python/src/xiaoqiao/gateway/server.py`（297 行） | stdio 版只实现了 `prompt` / `approval_response` 两个方法 | ⚠️ 不能直接复用它做 bridge，方法面差 60+ 个 |
| `python/pyproject.toml` | 21 个直接依赖；Python 3.14 | sidecar 打包可行（见 §5.5） |

### 2.3 关键判断：接缝在哪

前端与后端之间**只有一个接缝**：`GatewayService`。它对外暴露 `connect / on / call / send / sendPrompt / sendGroupMessage / sendApprovalResponse / cancel / close / isConnected`，内部只依赖 `new WebSocket(url)`。

因此桌面化**不需要改任何 store、组件或视图**，只需要：

1. 让 `connect()` 变成「先解析端点，再建连」；
2. 让「端点」可以来自 `window.tiny`，而不是常量。

这就是本方案能做到低风险的全部原因。

---

## 3. 方案对比与决策

### 3.1 三种集成形态

| | A0 包装模式 | **A1 本地页 + 直连 WS（推荐 MVP）** | A2 桥接去端口（目标形态） |
|---|---|---|---|
| `tinyjs.json` | `"url": "http://127.0.0.1:8766"` | `frontend.dist` 本地静态页 | 同 A1 |
| 页面如何取数据 | 现有 WebSocket | 现有 WebSocket（动态端口 + token） | `tiny.api.call(...)` → 外壳 → Python |
| HTTP 服务 | 必须保留 | 不要 | 不要 |
| 前端改动 | 0 | ~120 行（传输层 + 启动时序） | ~200 行 + Python 分发器重构 |
| 后端改动 | 0 | ~40 行（端口 0、token、ready 行） | ~300 行（抽 `Connection` 抽象） |
| 离线可用 | 否（依赖本机 HTTP 但可离线，勉强） | ✅ | ✅ |
| 有端口 | 是 | 是（临时端口） | **否** |
| 单实例/崩溃恢复/托盘 | 只能半套 | ✅ | ✅ |
| 工作量 | 1 人日 | 6–8 人日 | +4–5 人日 |
| 结论 | 只做 M0 冒烟 | **第一阶段落地** | **第二阶段收敛** |

### 3.2 决策

- **D1｜外壳走本地静态页（A1 → A2），不用 `url` 包装。** 包装模式把浏览器版原样塞进窗口，等于承认「桌面只是浏览器的皮肤」，拿不到单实例、托盘、自更新、离线。
- **D2｜第一阶段保留回环 WebSocket，第二阶段去端口。** 理由不是省事，而是 `gateway/server.py` 的 stdio 版只有 2 个方法，A2 必须先做「把 1800 行的 RPC 分发从 `_handle_ws` 里抽出来」的重构。这个重构值得做，但不该挡住第一个能用的版本。
- **D3｜Python 以 sidecar 随包**，不引入 Pyodide/转译，不重写运行时。
- **D4｜`--web` 浏览器模式保留**，桌面是新增目标而非替换。同一份 `web/` 产出两个消费者。
- **D5｜数据目录不变**（`~/.xiaoqiao`）。桌面版与 CLI 共享 `agent.db`、sessions、skills —— 这是产品优势（「命令行跑的长任务，桌面端能看到」），也让迁移成本为零。
- **D6｜Windows 优先。** 开发机是 Windows，tinyjs 的 Windows 后端（WebView2）是近期合入的分支，先把它跑顺；macOS 公证与 Linux WebKitGTK 放 M6。

### 3.3 为什么不选别的

| 方案 | 为什么不要 |
|---|---|
| Electron | 每装一次多 150–200 MB 的 Chromium；我们要的只是「一个窗口 + 系统集成」，代价过高 |
| Tauri | 技术上最接近（同样用系统 WebView、体积小），但要求 Rust 工具链并自带 IPC 设计；tinyjs 已经给了 JS 后端 + `tiny.api`，团队不必引入 Rust |
| PWA | 拿不到托盘常驻、全局快捷键、原生通知的可靠投递、自更新；而「关掉窗口也在跑的 Bot」是本产品核心 |
| 纯 `--web` + 浏览器快捷方式 | 无单实例、无系统集成，本质是书签 |

---

## 4. 目标架构

### 4.1 进程模型

```
xiaoqiao.exe (tinyjs launcher, C++)
  └─ tjs (txiki.js) ── src/backend/main.js        ← 我们写的编排层
       └─ spawn ── xiaoqiao-core.exe (Python)     ← PyInstaller sidecar
            └─ asyncio WS server on 127.0.0.1:<临时端口>
```

三层职责边界：

| 层 | 负责 | 不负责 |
|---|---|---|
| launcher（tinyjs 自带） | 窗口、菜单栏渲染、原生对话框、拖放、通知 | 业务 |
| `src/backend/main.js`（我们写，~300 行） | 拉起/守护 Python、把原生能力暴露成 `api.*`、菜单与托盘状态、日志 | 不碰任何 Agent 逻辑 |
| Python sidecar（现有代码 + 少量参数） | 全部现有能力：Agent、Bot、群聊、调度、审批、渠道、记忆 | 不提供静态文件服务（桌面模式） |
| 页面（现有 Vue） | UI | 只通过一个传输层说话 |

### 4.2 启动时序（这是最容易做错的地方）

```
launcher 起 ──► 窗口创建 ──► 页面加载（file://index.html）
                                    │
                                    ├─ 立即渲染骨架屏（「正在启动本地引擎…」）
                                    │
                                    └─ await tiny.api.call('gateway')  ──┐
                                                                        │
tjs 后端启动 ──► spawn python ──► 轮询 stderr ──► 读到                 │
                 "WS READY ws://127.0.0.1:54321"  ──► resolve({url, token}) ┘
                                                                        │
页面拿到端点 ──► new WebSocket(url) ──► 发送 auth 帧 ──► ready 事件 ──► 正常渲染
```

三条硬约束：

1. **页面先于 Python 就绪**。不能假设「窗口出来引擎就好了」。
2. **`tiny.api.call('gateway')` 必须在就绪后才 resolve**（不是立即返回 `{ready:false}` 的轮询），否则前端要自己写重试循环。
3. **冷启动预算**：Python 进程 + `agent-framework` 导入约 2–4 s，PyInstaller onefile 解包再 +1–3 s。启动画面是必需的，不是装饰。

### 4.3 目录结构

```
desktop/                          ← 新增，独立于 python/ 与 web/
  tinyjs.json
  assets/icon.png                 ← 1024×1024
  src/backend/
    main.js                       ← api 面、菜单、托盘、事件转发
    gateway.js                    ← Python 子进程守护 + ready 解析 + 重启退避
    menu.js                       ← 原生菜单定义
  .build/frontend/                ← pnpm build 的产物（gitignore）
  scripts/                        ← 打包脚本
```

`web/` 与 `python/` 不移动到 `desktop/` 下：它是第三个消费者，不是新的宿主。

### 4.4 `tinyjs.json`

```json
{
  "$schema": "https://tinyjs.app/schema/tinyjs.schema.json",
  "name": "xiaoqiao",
  "title": "小巧",
  "id": "app.xiaoqiao.desktop",
  "version": "0.1.0",
  "size": "1280x820",
  "minTinyjsVersion": "0.53",
  "frontend": {
    "build": "pnpm -C ../web exec vite build --outDir ../desktop/.build/frontend --emptyOutDir",
    "dist": ".build/frontend"
  },
  "api": {
    "preset": "none",
    "enable": ["gateway", "pickFolder", "openLogs", "restartGateway", "appInfo"]
  },
  "chrome": { "menu": true },
  "windows": { "icon": "assets/icon.png" },
  "update": { "url": "https://github.com/me9rez/xiaoqiao/releases/latest/download/manifest.json", "auto": "launch" }
}
```

三个要现场验证 / 特别小心的点：

- `frontend.dist` 指向项目内目录是安全的；**不要**写 `../web/dist`（`dist` 是否受路径安全规则约束未在 schema 中说明，绕开它省一次试错）。
- **`executables` 故意不写显式清单**：清单里「每个文件都必须是本 OS 的原生二进制」，跨平台列全会让另一个平台的 build 直接失败；不写则由 `executables/windows/`、`executables/macos/`、`executables/linux/` 自动按 OS 挑选，正是我们要的行为。
- `build` 直接调 `vite` 而不走 `pnpm build`：后者是 `run-p type-check "build-only {@}"`，`--outDir` 会同时灌给 `vue-tsc`。类型检查留在 CI 与本地 `pnpm type-check`，构建链只做构建。
- `api.preset: "none"` + `enable` 白名单：页面只能调到我们列出的方法，其余一律拒绝。

---

## 5. 关键设计

### 5.1 本地引擎的端口与鉴权

现状问题：固定 8765、无鉴权、`_free_port()` 会杀进程。

**Python 侧改动（约 40 行）**

```python
# main.py
parser.add_argument("--ws-port", type=int, default=None)      # 已存在
parser.add_argument("--auth-token", default=None)             # 新增；也可读 XIAOQIAO_TOKEN
parser.add_argument("--desktop", action="store_true")         # 新增：不启静态服务、不 free_port
```

```python
# ws_server.py::run_forever
async with serve(self._handle_ws, self._host, self._port) as server:
    self._port = self._bound_port(server)       # sockets[0].getsockname()[1]
    print(f"WS READY ws://{self._host}:{self._port}", file=sys.stderr, flush=True)
```

- **`--ws-port 0`**：内核分配临时端口，多实例互不干扰。
- **token 走环境变量**（`XIAOQIAO_TOKEN`），不走命令行 —— Windows 的进程列表对同用户可见，argv 会泄露。
- **鉴权握手**：连接建立后第一帧必须是 `{"method":"auth","params":{"token":"…"}}`；在此之前任何方法都返回 `{"type":"error","code":"unauthorized"}`。
- **`--desktop` 下禁用 `_free_port`**。这条是安全要求：现在的实现会 `Stop-Process` 掉占用 8765 的任意进程。
- 只在 `127.0.0.1` 绑定（已是默认）。

### 5.2 前端传输层抽象

目标：store / 组件 / 视图**零改动**。

```
web/src/services/
  gateway.ts        ← 保留导出名 gatewayService，内部改为委托 transport
  transport.ts      ← interface GatewayTransport
  wsTransport.ts    ← 现有 WebSocket 实现（浏览器 --web 模式）
  tinyTransport.ts  ← （A2 阶段）window.tiny 实现
  endpoint.ts       ← 端点解析：桌面 → tiny.api.call('gateway')；浏览器 → 默认 URL
```

```ts
// transport.ts
export interface GatewayTransport {
  connect(endpoint: GatewayEndpoint): Promise<void>
  send(raw: string): void
  on(event: string, cb: (payload: unknown) => void): () => void
  close(): void
  isConnected(): boolean
}

export interface GatewayEndpoint {
  url: string          // ws://127.0.0.1:54321
  token?: string       // 桌面模式必填
}
```

`main.ts` 的改动就一行性质：

```ts
const endpoint = await resolveGatewayEndpoint()   // 桌面：等引擎就绪；浏览器：常量
gatewayService.connect(endpoint)                  // 内部 await transport.connect
app.mount('#app')
```

`GatewayService.connect()` 在桌面模式下多一步：连上后先发 auth 帧，等 `ready` 事件再 `emit('open')`，让上层的「已连接」语义保持一致。

**顺带修掉的两个真问题**：`RPC_TIMEOUT_MS = 5000` 对 `previewPrompt`、`testChannel`（要走网络）太紧，桌面版把它提到 30 s；`messageQueue` 在拿不到端点时无限堆积，要加上限。

### 5.3 原生能力映射表

| 用户可见行为 | 现在（浏览器） | 桌面版实现 |
|---|---|---|
| 审批待办 | 只能盯着页面 | `approval_created` 事件 → `tiny.notify` + 托盘 badge 计数 |
| 长任务完成 | 页面内提示 | `done` 事件且窗口失焦 → 系统通知 |
| 新建会话 / 设置 / 退出 | 页面内按钮 | 原生菜单项 → `app.push('menu', id)` → 页面执行 |
| 选工作目录 | 手输路径 | `dialog` 原生面板 → `pickFolder` 返回路径 |
| 拖文件进对话 | 无 | `DROP` 事件 → 读真实路径 → 插入输入框 |
| 深浅色 | `matchMedia` 猜测 | `tiny.app.theme.get()` + `theme` 事件 → 写 `data-color-scheme` |
| 后台常驻 | 关标签页即断 | 托盘常驻；关窗口 = 隐藏，退出走菜单（`setHideOnClose(true)`） |
| 开机自启 | 无 | `app.launchAtLogin.set(true)`（设置项） |
| 长任务防止休眠 | 无 | `app.power.preventSleep`（Run 进行中） |
| 查日志 | 翻终端 | 菜单「打开日志」→ `shell.open` 日志目录 |

### 5.4 生命周期与崩溃恢复

| 场景 | 行为 |
|---|---|
| 正常关闭窗口 | `setHideOnClose(true)` → 隐藏到托盘，Python 继续跑（Run 不中断，这是产品要求） |
| 菜单「退出」 | 先给 Python 发 `shutdown`（或 SIGTERM），等 3 s，未退则强杀 |
| Python 崩溃 | 后端检测 exit code → 指数退避重启（1s/2s/4s，最多 3 次）→ 每次 `app.push('gateway-status', {...})` 让页面显示横幅 |
| 端口被占 / 启动失败 | 不做 `free_port`；把 stderr 尾部 20 行写日志并在页面弹出可复制的错误 |
| 二次启动（双击图标） | macOS 上 launcher 是 LaunchServices 注册进程，文档明确它会收到 single-instance 激活；**Windows 行为未写明**，M0 实测。若不支持，则在 backend 里用 `tjs.listen` 占一个命名锁，第二次启动直接 `app.show()` 并退出 |
| 机器重启后有未完成 Run | Python 侧现有逻辑（Run 落库）继续生效，页面显示「上次运行被中断」 |

### 5.5 Python sidecar 打包

**选 PyInstaller onefile**，理由与取舍：

- PyInstaller 6.22.3 的 classifiers 已含 `Python :: 3.14`（本次实测），不必换运行时。
- tinyjs 的 `executables/` 会把目录内的文件**压平**，onedir（含 `_internal/` 树）放不进去；onefile 是唯一零改造适配。
- onefile 的代价是每次启动解包（~1–3 s）。缓解：启动画面 + 后台预热。若实测不可接受，退路是把 onedir 树放进 `resources/xiaoqiao-core/` 再 `spawn`（Windows/Linux 可行；macOS 需额外处理签名与 JIT entitlement）。

```powershell
# scripts/build-desktop.ps1 的关键三段
uv run --project python pyinstaller python/desktop/xiaoqiao-core.spec --noconfirm
# 产物：desktop/executables/windows/xiaoqiao-core.exe
pnpm --dir web build --outDir desktop/.build/frontend --emptyOutDir
tinyjs build            # 出 desktop/dist/xiaoqiao/
```

`xiaoqiao-core.spec` 要点：

- `hiddenimports`：`agent_framework` 各 provider、`mcp`、`tzdata`（Windows 无 tz 数据库，已踩过）。
- 排除：`tkinter`、`unittest`、`pytest`、`web_dist`（桌面端不需要内嵌前端）。
- 体积预估 40–80 MB（待实测），是 tinyjs 6 MB 之外的不可避免成本。
- 打包后必须跑一次冒烟：`xiaoqiao-core.exe --ws-port 0 --desktop` 能否正常吐 `WS READY`。

---

## 6. 分阶段实施计划

| 阶段 | 内容 | 产出 | 人日 |
|---|---|---|---|
| **M0 冒烟** | 装 tinyjs；`tinyjs new` 一个 vue-ts 模板验证链路；把本仓库前端产物塞进去，验证 `file://` + WS 直连 | 一份「能不能做」的结论 + 5 个验证点全绿 | 1 |
| **M1 外壳打通** | `desktop/` 工程、`gateway.js` 守护、Python 三处参数改动、前端传输层 + 端点解析、`base: './'`、字体本地化 | 双击能起、能对话的 Windows 桌面版 | 3 |
| **M2 稳定性** | 崩溃重启、启动画面、错误横幅、日志文件、单实例、优雅退出 | 可日常使用（不自燃） | 2 |
| **M3 原生集成** | 菜单、托盘、通知、badge、文件夹选择、拖放、主题同步、防休眠 | 像桌面应用而不是套壳 | 3 |
| **M4 打包分发** | PyInstaller spec、`tinyjs build`、安装包、CI matrix、自更新 manifest | 可发给别人装的包 | 3 |
| **M5 去端口化** | 抽 `Connection` 抽象（WS / NDJSON over stdio 双实现）、`tinyTransport.ts`、删掉桌面路径上的 HTTP 与端口 | 零端口、页面无网络 | 4–5 |
| **M6 跨平台** | macOS 通用二进制 + 公证、Linux WebKitGTK + AppImage | 三平台 | 按需 |

**M0 的 5 个验证点**（任何一个失败都会改变方案）：

1. `file://` 下 Vite 产物（ES module + 相对路径）能加载，`#/chat` 路由正常。
2. 从 `file://` 页面 `new WebSocket('ws://127.0.0.1:8765')` 能连上（WebKit 对 file→ws 的策略）。
3. `localStorage` 在 `file://` 下可写（主题持久化依赖它）。
4. 中文输入法在 WebView2 里正常（IME 是嵌入式 WebView 的老问题）。
5. `file://` 下 `crypto.randomUUID()` 可用（`generateId` 依赖 secure context）。

---

## 7. 文件级改动清单

### 新增

| 文件 | 内容 |
|---|---|
| `desktop/tinyjs.json` | §4.4 |
| `desktop/src/backend/main.js` | `export const api = {...}`、`init(app)`、菜单/托盘/通知编排 |
| `desktop/src/backend/gateway.js` | spawn、stderr 解析、就绪 promise、重启退避、退出清理 |
| `desktop/src/backend/menu.js` | 菜单树 + `onMenu` 分发 |
| `desktop/assets/icon.png` | 1024×1024 |
| `desktop/README.md` | 开发/打包/排错 |
| `python/desktop/xiaoqiao-core.spec` | PyInstaller 配置 |
| `scripts/build-desktop.ps1` | 三段式构建 |
| `web/src/services/transport.ts` | 传输层接口 |
| `web/src/services/wsTransport.ts` | WebSocket 实现（从 gateway.ts 抽出） |
| `web/src/services/endpoint.ts` | 端点解析（桌面/浏览器分叉） |
| `web/src/types/tiny.d.ts` | `window.tiny` 类型声明（从 tinyjs 的 `types/tiny.d.ts` 裁剪） |
| `web/src/components/AppBootSplash.vue` | 启动画面 + 引擎启动失败可复制错误 |
| `docs/desktop-plan.md` | 本文 |

### 修改

| 文件 | 改动 |
|---|---|
| `web/src/services/gateway.ts` | 内部改为委托 transport；`connect(endpoint)` 异步；RPC 超时可配 |
| `web/src/main.ts` | 异步 bootstrap |
| `web/vite.config.ts` | `base: process.env.XIAOQIAO_DESKTOP ? './' : '/'` |
| `web/index.html` | 去掉 CDN 字体；`/icon.png` → `./icon.png` |
| `web/package.json` | 新增 `@fontsource-variable/schibsted-grotesk`、`@fontsource-variable/jetbrains-mono`；`build:desktop` 脚本 |
| `web/src/theme.ts` | 桌面端读 `tiny.app.theme`，订阅 `theme` 事件 |
| `python/src/xiaoqiao/main.py` | `--desktop`、`--auth-token`、`--ws-port 0`；桌面模式跳过 `_free_port` 与静态服务 |
| `python/src/xiaoqiao/gateway/ws_server.py` | auth 握手；`WS READY` 打印实际端口 |
| `python/pyproject.toml` | `[dependency-groups] desktop = ["pyinstaller>=6.22"]`（不进运行时依赖） |
| `.github/workflows/ci.yml` | 新增 `desktop` job（windows-latest：构建 sidecar + `tinyjs build`，仅上传 artifact，不签名） |
| `docs/design.md` | 新增 §14「桌面窗口」：若做自定义标题栏，新增 `--p-titlebar-h` 等 token，禁止硬编码 |
| `docs/status.md` | 增加桌面化交付定义与验证项 |

---

## 8. 验证矩阵

| 层 | 检查 | 命令/方法 |
|---|---|---|
| Python 单测 | 现有 192 项不回归 | `cd python && uv run pytest -q` |
| Python 新增 | 临时端口与 token 握手 | 新增 `test_ws_auth.py`：无 token 拒绝、错 token 拒绝、正确 token 通过、`--ws-port 0` 端口可读 |
| 前端单测 | transport 抽取后 store 行为不变 | `cd web && pnpm test:unit --run`（现有 59 项 + transport 单测） |
| 前端构建 | 相对路径产物 | `XIAOQIAO_DESKTOP=1 pnpm build` 后检查 `dist/index.html` 全是 `./assets/` |
| 桌面冒烟 | 起窗、对话、审批、重启引擎 | `tinyjs dev` + 手工清单 |
| 打包冒烟 | sidecar 能起、能吐 READY | `xiaoqiao-core.exe --ws-port 0 --desktop` |
| 安装冒烟 | 干净机器（无 Python）可安装可运行 | Windows 沙箱/VM |
| CI | 双 job 仍绿 + 新 desktop job | GitHub Actions |

---

## 9. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|---|
| R1 | `file://` 下 WS 或 ES module 被 WebKit 拦截 | 中 | 高（方案要改 A2 提前） | M0 第 1、2 点先验；失败则直接跳到 A2 桥接 |
| R2 | tinyjs Windows 后端仍不成熟（近期合入） | 中 | 中 | M0 只做链路验证；保留「先把 macOS/Linux 跑通」的退路；锁定版本，不用 latest |
| R3 | PyInstaller 打包后 agent-framework 动态导入失败 | 中 | 中 | spec 里显式 `hiddenimports`；打包后跑一遍 192 项单测的子集（`--collect` 漏了会立刻暴露） |
| R4 | 冷启动 5 s+ 体验差 | 高 | 中 | 启动画面 + 引擎预热；M2 测量分段耗时（解包/导入/DB 迁移） |
| R5 | 用户机器无 WebView2（Win10 老镜像） | 低 | 中 | 安装包内置 WebView2 bootstrapper（`tinyjs` 文档已有指引） |
| R6 | 系统 WebView 渲染差异导致 UI 走形 | 低（已审计 0 命中） | 中 | M3 用截图比对设计稿；`design.md` 约束仍是唯一依据 |
| R7 | 签名缺失触发 SmartScreen | 高 | 中（首发） | 先内部使用；对外分发前买 EV 证书或走 winget（接受首次警告） |
| R8 | 桌面端与 CLI 同时写 `agent.db` | 中 | 高（数据损坏） | SQLite 已是 WAL + busy_timeout；**M2 增加跨进程写锁/单实例提示**，或提供「只读打开」降级 |
| R9 | 无端口方案（A2）导致流式延迟可感 | 低 | 低 | A2 阶段实测 `text_delta` 端到端延迟；超 50 ms 就退回 A1 |

R8 需要单独强调：目前 `agent.db` 是单进程假设，桌面版让「CLI 和 GUI 同时开着」变成常态，这是**方案引入的新并发面**，必须在前两个阶段就处理，不能留到 P4。

---

## 10. 明确不做

- 不改写 Agent 运行时（不把 Python 逻辑搬到 JS）。
- 不做多窗口 / 多标签页（单窗口 + 托盘）。
- 不做移动端、不做 Web 端下线（`--web` 长期保留）。
- 不在第一阶段做 macOS 公证、Linux 打包、自动更新（M4/M6）。
- 不引入 Electron / Tauri 作为备选并存（选定 tinyjs 后不维护双外壳）。
- 不为桌面端单独设计一套 UI（沿用 `docs/design.md`，只补窗口相关 token）。

---

## 11. 待定问题

1. **桌面端是否需要独立的数据目录？** 现在方案是共享 `~/.xiaoqiao`（好处：与 CLI 共享；坏处：并发写，见 R8）。若短期解决不了并发，是否给桌面端一个 `~/.xiaoqiao/desktop.db`？
2. **关窗口 = 隐藏还是退出？** 产品语义上「Bot 要能后台跑」，但用户预期可能是「关掉就是关掉」。建议：首次关窗给一次性提示，之后按选择记住。
3. **API key 是否迁到系统凭据库**（`app.secrets`）？更安全，但 CLI 读不到，会破坏「CLI 与桌面共享配置」。
4. **是否给桌面端单独版本号**？`tinyjs.json` 的 `version` 与 Python 包版本是否同步（影响自更新判断）。
5. **M5 是否值得做**？如果 A1 的临时端口在实践中无感（多实例罕见、冲突为零），去端口化的收益主要是「页面无网络」的安全叙事，需要产品侧确认优先级。

---

## 12. 实施记录

### 12.1 M0 冒烟：五个验证点全部有结论

用一个自驱动页面（`inject` 的探针脚本 + `tiny.quit()`）在 `tinyjs dev` 里跑完，结果：

| 验证点 | 结果 |
|---|---|
| `file://` 下加载 Vite 产物 | ✅ 但**必须** `base: './'`：默认 `/assets/...` 全部 404，`#app` 为空 |
| `file://` → `ws://127.0.0.1` | ✅ 直连成功，`getSettings` 往返正常 |
| `localStorage` 在 `file://` 下 | ✅ 可写可读 |
| `crypto.randomUUID()` / `crypto.subtle` | ✅ 可用（`file://` 是 secure context） |
| ES module 从 `file://` 导入 | ✅ 动态 import 正常 |

实测数据：改用相对 base 重建后 `appChildren: 1`、`vueMounted: true`，即真实应用在 `file://` 下完整启动。

中文输入法（IME）无法自动断言，留作 M2 人工验收项。

### 12.2 M1 已完成

| 层 | 交付 |
|---|---|
| Python | `--desktop`（不启静态服务、不 `_free_port`）、`--ws-port 0` 取系统端口并打印实际值、`--auth-token`/`XIAOQIAO_TOKEN` 握手、`--exit-on-stdin-eof`、`shutdown` RPC、`WsGatewayServer.port` 与 `db_path`、`_stop_channels()` |
| 前端 | `services/endpoint.ts`（桌面问外壳、浏览器用常量）、`GatewayService.connect(endpoint)` + 握手期间消息排队 + `auth_failed` 事件、`main.ts` 先挂载再解析端点、`vite build --mode desktop` 相对 base、字体改为 npm 本地打包、修掉 `EmptyState.vue` 漏导入 `ChevronDown` |
| 外壳 | `desktop/`（`tinyjs.json`、`src/backend/{main,engine}.js`、`assets/icon.png`、`README.md`、`.gitignore`） |

验证：`pytest` **198 passed**、`vitest` **67 passed**、`ruff check/format` 干净、`pyright` 0 错误、`pnpm type-check` 通过、`vite build --mode desktop` 成功、`tinyjs dev` 与 `tinyjs build` 均跑通；打包产物 `desktop/dist/xiaoqiao.exe` 启动后日志出现 `Client connected` + `Client authenticated`；强杀外壳后引擎进程立即退出、端口释放（无孤儿）。

### 12.3 与方案的偏差（有意为之）

1. **没有引入 `GatewayTransport` 接口**，只做了 `endpoint.ts` + 握手。理由：方案里的接口是为了 A2 的第二个实现；现在只有 WebSocket 一个消费者，加接口只是空转。A2 落地时再抽，届时 `wsTransport.ts` 与 `tinyTransport.ts` 同时出现才有意义。
2. **开发态走 `devUrl`（http://127.0.0.1:5173），不是 `file://`**。`tinyjs dev` 在没有 `dev`/`devUrl` 时只会去找 `src/frontend/index.html`，忽略 `frontend.dist`。`file://` 路径由 `tinyjs build` 出的产物覆盖验证（已验证）。
3. **生命周期用 stdin EOF，而不是发 `shutdown` RPC**。外壳以 `stdin: "pipe"` 启动引擎并传 `--exit-on-stdin-eof`，外壳一死管道就 EOF，引擎自行退出——跨平台、无需 pid 轮询。`shutdown` RPC 仍然保留给"优雅退出"场景。
4. **`--ws-port 0` 原本是坏的**：`main.py` 里 `if args.ws_port:` 把 `0` 当假值，会掉进 stdio 模式。已改成 `is not None`。
5. **`WsGatewayServer` 新增 `db_path` 参数**：测试需要（不碰真实库），也顺带为 R8 的多实例方案留了口子。

### 12.4 M1 之后仍未做

- M2：托盘常驻、单实例、启动画面、错误横幅、日志文件（`engine.log` 已写但未验证格式）、IME 人工验收、R8 并发写库
- M3：原生菜单、审批通知、文件夹选择、拖放、主题同步
- M4：PyInstaller sidecar（现在打包版仍靠本机 `uv` 找引擎，只在开发机成立）、安装包、自更新
- 图标仍是 64×64 放大到 1024×1024，正式发布前需重绘

