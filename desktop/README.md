# 小巧桌面外壳（tinyjs）

把 `web/` 的构建产物放进 tinyjs 的原生窗口，由本目录的 JS 后端拉起并守护
`python/` 里的引擎进程。前端与引擎之间的协议完全不变——仍然是那套 WebSocket
JSON-RPC，只是端点由外壳分配。

## 组成

```
desktop/
  tinyjs.json            # 窗口、前端构建/开发命令、后端入口
  assets/icon.png        # 应用图标
  src/backend/main.js    # api 面（gateway / engineStatus / restartEngine / appInfo / openDataDir）
  src/backend/engine.js  # 引擎子进程：spawn、就绪解析、崩溃重启、日志尾
  resources/python/      # 独立 CPython + 已安装依赖（构建产物，gitignore）
  .build/frontend/       # pnpm 构建产物（gitignore）
```

`resources/python` 是打包版的引擎来源：`uv python install` 下载的
python-build-standalone（onedir），`xiaoqiao` 与依赖装进它自己的
site-packages。开发模式不需要它。

## 开发

前置：`tinyjs`（`irm https://tinyjs.app/install.ps1 | iex`）、`uv`、`pnpm`。

```powershell
cd desktop
tinyjs dev
```

`tinyjs dev` 会：

1. 起 Vite 开发服务器（`http://127.0.0.1:5173`，带 HMR）；
2. 起本目录的后端，后者执行 `uv run --project ../python python -m xiaoqiao.main --desktop --ws-port 0`；
3. 打开原生窗口，页面加载后向 `tiny.api.call('gateway')` 要端点。

终端里应该看到：

```
[shell] starting dev engine (cwd=<repo>)
[engine] WS READY ws://127.0.0.1:<port>
[shell] engine ready at ws://127.0.0.1:<port>
[engine] INFO xiaoqiao.gateway.ws_server: Client connected from ('127.0.0.1', …)
[engine] INFO xiaoqiao.gateway.ws_server: Client authenticated
```

## 构建

```powershell
# 在仓库根目录：下载独立 Python → 装 wheel → tinyjs build
.\scripts\build-desktop.ps1
```

产物 `desktop/dist/`（约 136 MB，含 `resources/python`）。重复构建时加
`-SkipRuntime` 复用已有运行时，只重建前端与应用。

只跑 `tinyjs build` 也能出包，但 `resources/python` 不在时打包版会退回开发分支（依赖本机 `uv`）。

## 契约（改这里前先读）

| 关注点 | 做法 |
|---|---|
| 端口 | 引擎用 `--ws-port 0` 让系统分配；外壳从 `--ready-file` 写的 `{"url","pid"}` 读实际端口（stderr 的 `WS READY` 仍在，仅作兜底） |
| 鉴权 | 外壳生成 24 字节随机 token，经环境变量 `XIAOQIAO_TOKEN` 传给引擎；页面连上后第一帧必须是 `{"method":"auth","params":{"token":…}}`，否则引擎回 `unauthorized` 并以 4401 关闭 |
| 就绪语义 | `api.gateway()` **只在引擎真正监听后** resolve，页面不需要自己重试 |
| 生命周期 | 外壳以 `stdin: "pipe"` 启动引擎，并传 `--exit-on-stdin-eof`；外壳死掉 → 管道 EOF → 引擎自行退出（3 s 未退则看门狗硬退出），不留孤儿进程 |
| 崩溃恢复 | 引擎非预期退出后按 1s/2s/4s 退避重启，最多 3 次，状态经 `engine-status` 推送 |
| 数据目录 | 不变，仍是 `~/.xiaoqiao`，与 CLI 共享 bot / 会话 / 记忆 |
| 托盘 | `app.tray.set(...)` 成功后才 `setHideOnClose(true)`：关窗=隐藏，引擎继续跑；菜单 = 显示 / 重启引擎 / 打开数据目录 / 退出。Linux 跳过（托盘依赖 libayatana） |
| 日志 | 引擎输出写到 `paths.logs/engine.log`（Windows：`%LOCALAPPDATA%\app.xiaoqiao.desktop\Logs\`），每行带 ISO 时间戳，保留最近 400 行。注意 `app.paths()` **没有 `userData`** 字段 |
| 单实例 | tinyjs launcher 自带：重复启动不会再开一个窗口，也不会再拉一个引擎 |
| 后台工作槽 | 引擎启动时抢 `127.0.0.1:8760`；抢不到就进入 **passive** 模式（只服务 WS，不跑调度器/渠道）。这样桌面端与 CLI 同开时定时任务不会重复触发 |

## 已知缺口（按 `docs/desktop-plan.md` 的里程碑排期）

- M4 剩余：安装包（MSI/NSIS 或 zip）与自更新 manifest（`tinyjs publish`）
- 中文输入法（IME）人工验收
- 图标目前是 64×64 放大到 1024×1024，正式发布前需要重绘

## 原生集成（M3）

| 能力 | 入口 | 说明 |
|---|---|---|
| 应用菜单 | `tiny.menu.set([...])` | **菜单在 `tiny.menu`，不在 `tiny.app.menu`**（后者是 `undefined`，写错是静默空操作） |
| 菜单点击 | `tiny.menu.on(id)` | id：`new-session` / `open-settings` / `open-data-dir` / `reload` / `toggle-theme` / `quit` |
| 通知 | `tiny.notify(...)` | 只在窗口失焦时弹；审批按 approvalId 去重 |
| 拖放 | `tiny.win.onDrop(paths)` | 真实路径经 `services/composer.ts` 追加到输入框 |
| 选目录 | `tiny.dialog.pickFolder()` | Bot 编辑器的「选择…」，仅桌面模式显示 |
| 主题 | `tiny.theme.get()/on()` | 仅当偏好为 `system` 时覆盖 `matchMedia` |

## 排错

| 现象 | 处理 |
|---|---|
| `tinyjs: frontend dev server did not respond at http://127.0.0.1:5173` | Vite 绑到了 `localhost`（IPv6），命令里已固定 `--host 127.0.0.1`；若仍失败先确认 5173 没被占用 |
| 窗口空白 | 检查是否用了 `--mode desktop` 构建；`file://` 下绝对路径 `/assets/*` 全部失效 |
| `tinyjs build` 报 `EEXIST: file already exists` | 上一次运行的 `xiaoqiao.exe` 还活着，锁住了 `dist/`。先结束进程再构建 |
| 引擎连上又立刻断开 | token 不匹配；确认页面拿到的是 `api.gateway()` 返回的 token，而不是旧实例的 |
| 日志里出现 `running in passive mode` | 另一个引擎（多半是 CLI）已经占着后台工作槽；当前实例只处理界面请求。想让桌面端接管，先退出那个进程 |
| `engine did not report ready in time` | 看 `engine.log` 尾部；常见原因是 `uv` 不在 PATH，或 `python/` 依赖没 sync |

