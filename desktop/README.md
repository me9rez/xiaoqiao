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
  .build/frontend/       # pnpm 构建产物（gitignore）
```

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
cd desktop
tinyjs build          # 产物在 desktop/dist/
```

`tinyjs build` 调用 `tinyjs.json` 里的 `frontend.build`（`vite build --mode desktop`，
把 URL 变成相对路径，`file://` 下才能加载），再把 `dist/` 打进应用。

## 契约（改这里前先读）

| 关注点 | 做法 |
|---|---|
| 端口 | 引擎用 `--ws-port 0` 让系统分配；外壳从 stderr 的 `WS READY ws://host:port` 读实际端口 |
| 鉴权 | 外壳生成 24 字节随机 token，经环境变量 `XIAOQIAO_TOKEN` 传给引擎；页面连上后第一帧必须是 `{"method":"auth","params":{"token":…}}`，否则引擎回 `unauthorized` 并以 4401 关闭 |
| 就绪语义 | `api.gateway()` **只在引擎真正监听后** resolve，页面不需要自己重试 |
| 生命周期 | 外壳以 `stdin: "pipe"` 启动引擎，并传 `--exit-on-stdin-eof`；外壳死掉 → 管道 EOF → 引擎自行退出，不留孤儿进程 |
| 崩溃恢复 | 引擎非预期退出后按 1s/2s/4s 退避重启，最多 3 次，状态经 `engine-status` 推送 |
| 数据目录 | 不变，仍是 `~/.xiaoqiao`，与 CLI 共享 bot / 会话 / 记忆 |
| 托盘 | `app.tray.set(...)` 成功后才 `setHideOnClose(true)`：关窗=隐藏，引擎继续跑；菜单 = 显示 / 重启引擎 / 打开数据目录 / 退出。Linux 跳过（托盘依赖 libayatana） |
| 日志 | 引擎输出写到 `paths.logs/engine.log`（Windows：`%LOCALAPPDATA%\app.xiaoqiao.desktop\Logs\`），每行带 ISO 时间戳，保留最近 400 行。注意 `app.paths()` **没有 `userData`** 字段 |
| 单实例 | tinyjs launcher 自带：重复启动不会再开一个窗口，也不会再拉一个引擎 |
| 后台工作槽 | 引擎启动时抢 `127.0.0.1:8760`；抢不到就进入 **passive** 模式（只服务 WS，不跑调度器/渠道）。这样桌面端与 CLI 同开时定时任务不会重复触发 |

## 已知缺口（按 `docs/desktop-plan.md` 的里程碑排期）

- M3：原生菜单、审批通知、文件夹选择、拖放、主题同步、中文输入法人工验收
- M4：PyInstaller sidecar（`executables/`）、安装包、自动更新
- 图标目前是 64×64 放大到 1024×1024，正式发布前需要重绘

## 排错

| 现象 | 处理 |
|---|---|
| `tinyjs: frontend dev server did not respond at http://127.0.0.1:5173` | Vite 绑到了 `localhost`（IPv6），命令里已固定 `--host 127.0.0.1`；若仍失败先确认 5173 没被占用 |
| 窗口空白 | 检查是否用了 `--mode desktop` 构建；`file://` 下绝对路径 `/assets/*` 全部失效 |
| `tinyjs build` 报 `EEXIST: file already exists` | 上一次运行的 `xiaoqiao.exe` 还活着，锁住了 `dist/`。先结束进程再构建 |
| 引擎连上又立刻断开 | token 不匹配；确认页面拿到的是 `api.gateway()` 返回的 token，而不是旧实例的 |
| 日志里出现 `running in passive mode` | 另一个引擎（多半是 CLI）已经占着后台工作槽；当前实例只处理界面请求。想让桌面端接管，先退出那个进程 |
| `engine did not report ready in time` | 看 `engine.log` 尾部；常见原因是 `uv` 不在 PATH，或 `python/` 依赖没 sync |
