# 设计规范

> **本文件是 `web/` 的唯一设计依据。** 新增或修改任何界面之前先读这里；实现与本文冲突时，以本文为准。
>
> - 来源：从 [MoonshotAI/kimi-code · apps/kimi-code/dist-web](https://github.com/MoonshotAI/kimi-code/tree/main/apps/kimi-code/dist-web) 的生产构建产物解析生成（2026-10-17），本仓库将其采纳为设计基线。
> - 直接来源：`index.html`、`assets/index-CY1AHs2J.css`（648 KB）、`boot.js`；该仓库没有 Web UI 源码，`dist-web` 是唯一可用的设计源。
> - 颜色、尺寸、动效等数值直接取自 CSS 自定义属性；设计原则、组件用法和 Do/Don't 为归纳内容。
> - 构建产物共 521 个根级自定义属性、95 个暗色主题覆盖、2,758 个 class 名。

## 0. 在本项目中的落地约定

| 约定 | 位置 | 说明 |
| --- | --- | --- |
| Token 定义 | `web/src/styles/tokens.css` | 唯一的 token 来源，含暗色覆盖与字号缩放 |
| 主题接管 | `html[data-color-scheme]` / `html[data-font-scale]` | 首屏由 `web/index.html` 内联脚本提前设置，避免闪烁 |
| 运行时切换 | `web/src/theme.ts` | 读写 `localStorage`，监听系统主题变化 |
| 偏好入口 | 设置 → 偏好（`SettingsPreferencesView.vue`） | 浅色 / 深色 / 跟随系统，四档字号 |
| 旧变量 | `tokens.css` 末尾的兼容别名 | `--bg-page`、`--border` 等仅作过渡，新代码禁止使用 |
| 字体 | 拉丁与数字用 Schibsted Grotesk，中文回退系统字体 | 首屏只加载拉丁可变字体，避免中文字库的百级子集请求 |
| 图标 | `@lucide/vue` | 尺寸遵循 §12 的 14 / 16 / 18 / 20 / 28 |
| 群聊扩展 | §13 | **本仓库新增**，非 dist-web 解析结果；只允许使用既有 token 与组件私有 `--p-*` |

实现规则：组件里只写 `var(--token)`，不写死十六进制；暗色只覆盖语义 token；边框默认 `--p-hairline`；状态色必须「底色 + 边框 + 文字」成套使用。

---

## 1. 设计定位

Kimi Code Web 是一个高密度、低干扰的 AI 编码工作台，视觉语言可以概括为：

| 原则 | 具体表现 |
| --- | --- |
| 中性底色，单一强调色 | 界面几乎全部由黑、白、灰构成，蓝色只用于主操作、选中态、链接和焦点 |
| 用表面分层，而不是重边框 | `bg → surface → surface-raised` 三级明度差，配合 0.5px 发丝线 |
| 紧凑但不拥挤 | 14px 基准字号，按钮 24–42px，菜单行高约 28px |
| 轻量材质感 | 半透明菜单 + 24px 背景模糊、32px 超大圆角输入框、超椭圆转角 |
| 克制的动效 | 大部分过渡 120–160ms，只做颜色、透明度、2px 位移和 0.97 缩放 |
| 双主题对等 | 暗色不是简单反色：表面层级、阴影、强调色、边框透明度都单独定义 |

关键的“签名”细节：

- `--p-hairline: .5px`：所有边框默认半像素，不是 1px。
- 输入框 `--radius-composer: 32px` + `corner-shape: superellipse(1.5)`。
- 菜单背景 95% 不透明 + `blur(24px) saturate(1.8)`。
- 焦点环 3px 柔和蓝色光晕，强版本再加 1px 实线。
- 字体使用 450/475/525 等中间字重，不是常见的 400/500/600/700 四档。

---

## 2. Token 架构

### 2.1 命名分层

| 层级 | 前缀 | 作用 |
| --- | --- | --- |
| 语义颜色 | `--color-*` | 主题切换的唯一入口 |
| 间距 | `--space-*` | 2/4/6/8/12/16/20/24/32 |
| 字号 | `--text-*`、`--ui-*`、`--md-*` | 组件字号、UI 阶梯、Markdown 阶梯 |
| 字重 | `--weight-*` | 400 / 450 / 475 / 500 / 525 / 600 / 700 |
| 行高 | `--leading-*` | 1 / 1.25 / 1.4 / 1.5 / 1.6 / 1.7 |
| 圆角 | `--radius-*` | 4–32px 与 999px |
| 阴影 | `--shadow-*` | xs / sm / md / lg / xl / menu / input / send |
| 动效 | `--duration-*`、`--ease-*` | 120/160/260ms 等 |
| 层级 | `--z-*` | 0–9999 |
| 组件私有 | `--p-*`、`--menu-*`、`--panel-*`、`--composer-*`、`--code-*` | 组件内部尺寸，不跨组件复用 |

### 2.2 主题与偏好切换

主题通过 `<html>` 上的属性切换，并在首屏脚本 `boot.js` 中提前应用，避免闪烁：

```html
<html lang="en" data-color-scheme="light|dark|system"
      data-font-scale="small|medium|large|xlarge">
```

持久化键：

- `kimi-web.color-scheme` → `light` / `dark` / `system`
- `kimi-web.font-scale` → `small` / `medium` / `large` / `xlarge`
- 旧版 `kimi-web.ui-font-size`（px）会迁移到最接近的字号档位

页面还声明了：

```html
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121212" media="(prefers-color-scheme: dark)">
```

实现规则：只在 `html[data-color-scheme=...]` 层覆盖语义 token，组件 CSS 不写死主题色。

---

## 3. 颜色

### 3.1 核心表面与文字

| Token | Light | Dark | 用途 |
| --- | --- | --- | --- |
| `--color-bg` | `#ffffff` | `#121212` | 页面底色 |
| `--color-surface` | `#f5f5f5` | `#1f1f1f` | 分组区域、次级表面 |
| `--color-surface-raised` | `#ffffff` | `#292929` | 卡片、弹窗、菜单、Toast |
| `--color-surface-overlay` | `#ffffff` | `rgba(255,255,255,.1)` | 输入框等浮起表面 |
| `--color-surface-sunken` | `#f5f5f5` | `#121212` | 内凹区域、分段控件底槽 |
| `--color-surface-deep` | `#f5f5f5` | `#0d0d0d` | 最深层的侧栏/边框区域 |
| `--color-well` | `#f5f5f5` | `#1f1f1f` | 凹陷容器 |
| `--color-sidebar-bg` | `#f9fbfc` | `#0d0d0d` | 侧边栏 |
| `--color-user-bubble-bg` | `#f5f5f5` | `#292929` | 用户消息气泡 |
| `--color-text-strong` | `#000000` | `#ffffff` | 最高对比文字 |
| `--color-text` | `rgba(0,0,0,.95)` | `rgba(255,255,255,.9)` | 正文 |
| `--color-text-muted` | `rgba(0,0,0,.68)` | `rgba(255,255,255,.64)` | 次要文字、图标 |
| `--color-text-faint` | `rgba(0,0,0,.53)` | `rgba(255,255,255,.5)` | 占位符、弱提示 |
| `--color-text-quaternary` | `rgba(0,0,0,.3)` | `rgba(255,255,255,.26)` | 极弱装饰文字 |
| `--color-line` | `rgba(0,0,0,.13)` | `rgba(255,255,255,.12)` | 默认边框、分隔线 |
| `--color-line-strong` | `rgba(0,0,0,.15)` | `rgba(255,255,255,.18)` | 控件边框 |
| `--color-hover` | `rgba(0,0,0,.03)` | `rgba(255,255,255,.05)` | 悬停背景 |
| `--color-selected` | `rgba(0,0,0,.05)` | `rgba(255,255,255,.1)` | 选中背景 |
| `--color-selected-hover` | `rgba(0,0,0,.08)` | `rgba(255,255,255,.14)` | 选中悬停 |

### 3.2 强调色与状态色

| Token | Light | Dark |
| --- | --- | --- |
| `--color-accent` | `#1783ff` | `#1a88ff` |
| `--color-accent-hover` | `#167ff7` | `#258eff` |
| `--color-accent-soft` | `#e8f3ff` | `rgba(26,136,255,.1)` |
| `--color-accent-bd` | `rgba(23,131,255,.25)` | `rgba(26,136,255,.28)` |
| `--color-success` | `#0e7a38` | `#3fb950` |
| `--color-success-soft` | `#e7f6ee` | `rgba(63,185,80,.14)` |
| `--color-success-bd` | `#bfe3cc` | `rgba(63,185,80,.28)` |
| `--color-warning` | `#a9610a` | `#d29922` |
| `--color-warning-soft` | `#fbf1e0` | `rgba(210,153,34,.14)` |
| `--color-warning-bd` | `#f0d9b8` | `rgba(210,153,34,.28)` |
| `--color-orange` | `#bc4c00` | `#f0883e` |
| `--color-orange-soft` | `#fff1e5` | `rgba(240,136,62,.14)` |
| `--color-danger` | `#c0392b` | `#f85149` |
| `--color-danger-soft` | `#fbeaea` | `rgba(248,81,73,.14)` |
| `--color-danger-bd` | `#f0cccc` | `rgba(248,81,73,.28)` |
| `--color-done` | `#8250df` | `#a371f7` |
| `--color-done-soft` | `#f3e8ff` | `rgba(163,113,247,.14)` |
| `--color-done-bd` | `#e0ccff` | `rgba(163,113,247,.28)` |
| `--color-info` | `#1783ff` | `#1a88ff` |
| `--color-attention` | `#ff9f0a` | — |

### 3.3 Diff、代码与发送按钮

| Token | Light | Dark |
| --- | --- | --- |
| `--color-diff-add-bg` | `rgba(22,196,86,.1)` | `rgba(63,185,80,.14)` |
| `--color-diff-del-bg` | `rgba(255,77,77,.1)` | `rgba(248,81,73,.14)` |
| `--color-diff-add-fg` | `#16c456` | `#16c456`（未覆盖） |
| `--color-diff-del-fg` | `#ff4756` | `#ff4756`（未覆盖） |
| `--color-send-bg` | `rgba(0,0,0,.9)` | `rgba(255,255,255,.84)` |
| `--color-send-bg-hover` | `#252525` | `rgba(255,255,255,.848)` |
| `--color-send-icon` | `#ffffff` | `#1f1f1f` |
| `--color-send-bg-disabled` | `rgba(0,0,0,.05)` | `rgba(255,255,255,.1)` |
| `--color-send-icon-disabled` | `rgba(0,0,0,.27)` | `rgba(255,255,255,.28)` |
| `--color-composer-bg` | `#ffffff` | `#1f1f1f` |
| `--color-composer-line` | `rgba(0,0,0,.13)` | `rgba(255,255,255,.12)` |
| `--color-composer-focus-line` | `rgba(0,0,0,.25)` | `rgba(255,255,255,.25)` |

### 3.4 使用规则

- **蓝色只表达“可操作/已选中/有焦点”**，不用于装饰性大面积填充。
- 状态色必须“底色 + 边框 + 文字”成套使用：`*-soft` 作背景、`*-bd` 作边框、主色作文字。
- 不要把 `--color-accent` 当成功色或信息色；它们数值相同但语义不同。
- 文字层级优先用 token，不要用 `opacity` 模拟弱化文字；`opacity: .5` 只用于禁用态。
- 暗色主题的浮层背景使用 `rgba(255,255,255,.1)` 这类半透明白，而不是继续加灰。
- 选择背景：`--p-selection: rgba(23,131,255,.2)`（暗色 `rgba(26,136,255,.2)`）。

---

## 4. 字体与排版

### 4.1 字体栈

```css
--font-ui-latin: "Schibsted Grotesk Variable", "Helvetica Neue", Arial;
--font-ui: var(--font-ui-latin), "Noto Sans SC Variable", "Noto Sans SC",
  "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Sans SC",
  -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, sans-serif,
  "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji";
--font-display: var(--font-ui);
--font-mono: "JetBrains Mono Variable", "JetBrains Mono", ui-monospace,
  "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
--font-kbd: "Schibsted Grotesk Variable", system-ui, sans-serif;
```

- UI 与正文统一使用 `--font-ui`，标题不单独换字体。
- 代码、行内代码、终端使用 `--font-mono`。
- 快捷键帽使用 `--font-kbd`。

### 4.2 UI 字号阶梯（`data-font-scale=medium`，基准 14px）

| Token | 字号 | 行高 | 典型用途 |
| --- | --- | --- | --- |
| `--ui-t0` / `--text-2xl` | 20px（上限 24px） | 28px | 页面级标题 |
| `--ui-t1` / `--text-xl` | 18px（上限 22px） | 26px | 区块标题 |
| `--ui-t2` / `--text-lg` | 16px | 24px | 卡片标题、对话框标题 |
| `--ui-b1` | 15px | 22px | 强调正文 |
| `--ui-b2` / `--text-base` | 14px | 20px | 默认正文、按钮 |
| `--text-sm` | 13px | 继承 | 菜单项、说明文字 |
| `--ui-c1` / `--text-xs` | 12px | 18px | 辅助信息、徽标 |
| `--text-2xs` | 11px | 继承 | 极小标签 |
| `--ui-c2` | 10px | 14px | 角标、计数器 |

字号缩放档位：

| `data-font-scale` | `--base-font` | 行为 |
| --- | --- | --- |
| `small` | 12px | 所有 UI 字号减去 2px |
| `medium` | 14px | 默认 |
| `large` | 16px | 所有 UI 字号增加 2px |
| `xlarge` | 18px | 所有 UI 字号增加 4px；t0 封顶 24px，t1 封顶 22px |

实现方式：`--ui-shift: calc(var(--base-font, 14px) - 14px)`，各字号为 `calc(基准px + var(--ui-shift))`。Markdown 使用独立的 `--markdown-font-scale`（12/14、1、16/14、18/14）。

### 4.3 字重

| Token | 值 | 用途 |
| --- | --- | --- |
| `--weight-regular` | 400 | 正文、Markdown |
| `--weight-caption` | 450 | 图注、弱说明 |
| `--weight-option-label` | 475 | 菜单选项 |
| `--weight-medium` | 500 | 按钮、卡片标题、对话框标题 |
| `--weight-ui-strong` | 525 | 强调的 UI 文本 |
| `--weight-section-label` | 600 | 区块标签、Markdown 强调 |
| `--weight-semibold` | 700 | 面板标题、Markdown H1 |

不要把这些中间字重四舍五入成 400/500/600，变量字体下它们有可见差异。

### 4.4 Markdown 排版

| 元素 | 规格 |
| --- | --- |
| 正文 | 14px / 22px（`22/14`），400 |
| H1 | 20px / 1.6，700 |
| H2 | 18px / `28/18`，600 |
| H3 | 16px / 1.625，600 |
| 代码 | JetBrains Mono 14px / 22px |
| 图注 | 12px / 1.5 |
| 段间距 | 1rem |
| 块级元素间距 | 0.75rem |
| 标题前距 | 1.25rem |
| 列表缩进 | 1.5rem，条目间距 0.5rem |
| 引用 | 左侧 2px 圆角竖线，缩进 1.5rem |
| 行内代码 | 4px 圆角，左右 4px 内边距，背景 `--color-selected` |
| 代码块 | 16px 圆角，最大高度 500px，头部最小 32px，内边距 16px |
| 表格 | 单元格 0.5em / 0.75em，表头使用 `--color-surface` |
| 字距 | 0 |

链接色在 Markdown 中单独定义：亮色 `#0f6ef2`，暗色 `#3393ff`。

---

## 5. 间距、圆角、描边与高度

### 5.1 间距

| Token | 值 | 用途 |
| --- | --- | --- |
| `--space-05` | 2px | 微调、图标与文字的最小间隙 |
| `--space-1` | 4px | 紧凑内间距 |
| `--space-1-5` | 6px | 徽标、快捷键帽 |
| `--space-2` | 8px | 常规图标/文字间距 |
| `--space-3` | 12px | 控件内边距、卡片内容间距 |
| `--space-4` | 16px | 卡片内边距、区块间距 |
| `--space-5` | 20px | 大按钮内边距 |
| `--space-6` | 24px | 页面/对话框外边距 |
| `--space-8` | 32px | 大区块、发送按钮尺寸 |

规则：优先使用 4 的倍数；2px 只用于视觉校正；不要引入 10/14/18 等不在阶梯中的值（组件内部明确规定的除外）。

### 5.2 圆角

| Token | 值 | 用途 |
| --- | --- | --- |
| `--radius-xs` | 4px | 快捷键帽、行内代码、文字按钮 |
| `--radius-sm` | 6px | 小按钮、小输入框、徽标 |
| `--radius-md` | 8px | 默认按钮、输入框、横幅、分段控件 |
| `--radius-lg` | 12px | 卡片、菜单、Toast |
| `--radius-xl` | 16px | 对话框、代码块 |
| `--radius-2xl` | 20px | 超大容器 |
| `--radius-composer` | 32px | 输入框外壳 |
| `--radius-full` | 999px | 胶囊、圆形按钮、滚动条 |
| `--radius-window` | 14px | 桌面窗口控件 |
| `--radius-dock-pill` | 10px | Dock 胶囊 |

派生圆角使用减法保持同心：菜单项 `12 - 3.5 - 0.5 = 8px`，下拉行约 6.5px。

### 5.3 描边与焦点

| Token | 值 |
| --- | --- |
| `--p-hairline` | `0.5px` |
| `--p-focus-ring-w` | `3px` |
| `--p-focus-ring` | `0 0 0 3px var(--color-accent-soft)` |
| `--p-focus-ring-strong` | `0 0 0 3px var(--color-accent-soft), 0 0 0 1px var(--color-accent)` |
| `--p-ring-stroke` | `1.5px` |

- 所有可交互元素使用 `:focus-visible`，不要用 `:focus` 画自定义焦点。
- 默认边框一律 `var(--p-hairline) solid var(--color-line)`。
- 控件边框用 `--color-line-strong`。
- 焦点态不能只换边框颜色，必须同时有外环。

### 5.4 阴影

| Token | Light | Dark |
| --- | --- | --- |
| `--shadow-xs` | `0 1px 2px rgba(16,24,40,.04)` | `0 1px 2px rgba(0,0,0,.2)` |
| `--shadow-sm` | `0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06)` | `0 1px 2px rgba(0,0,0,.22), 0 1px 3px rgba(0,0,0,.18)` |
| `--shadow-md` | `0 4px 12px rgba(16,24,40,.07), 0 2px 4px rgba(16,24,40,.05)` | `0 4px 12px rgba(0,0,0,.3), 0 2px 4px rgba(0,0,0,.24)` |
| `--shadow-lg` | `0 12px 32px rgba(16,24,40,.12), 0 4px 10px rgba(16,24,40,.08)` | `0 12px 32px rgba(0,0,0,.34), 0 4px 10px rgba(0,0,0,.28)` |
| `--shadow-xl` | `0 24px 64px rgba(16,24,40,.18), 0 8px 20px rgba(16,24,40,.1)` | `0 24px 64px rgba(0,0,0,.42), 0 8px 20px rgba(0,0,0,.32)` |
| `--shadow-menu` | 三层黑 alpha（lch） | `0 6px 18px rgba(0,0,0,.2), 0 3px 9px rgba(0,0,0,.24), 0 1px 1px rgba(0,0,0,.24)` |
| `--shadow-input` | `0 5px 16px -4px rgba(0,0,0,.07)` | 同亮色 |
| `--shadow-send` | `0 7px 16px -13px rgba(0,0,0,.38), 0 1px 2px rgba(0,0,0,.07)` | 同亮色 |

暗色主题的阴影更黑、更重，否则在深色底上不可见。菜单和弹窗同时使用阴影 + 发丝线，避免只靠阴影分层。

---

## 6. 动效

### 6.1 时长与曲线

| Token | 值 | 用途 |
| --- | --- | --- |
| `--duration-fast` | `0.12s` | 悬停、按下、退出 |
| `--duration-base` | `0.16s` | 常规状态切换、菜单进入 |
| `--duration-slow` | `0.26s` | 对话框、面板进入 |
| `--duration-hover-intent` | `0.25s` | 悬停意图延迟 |
| `--duration-tooltip` | `0.3s` | Tooltip |
| `--duration-spin` | `0.7s` | 加载旋转 |
| `--duration-flash` | `1.2s` | 高亮闪烁 |
| `--ease-out` | `cubic-bezier(.16, 1, .3, 1)` | 默认进入/悬停曲线 |
| `--ease-in-out` | `cubic-bezier(.4, 0, .2, 1)` | 对称过渡 |

### 6.2 动效模式

- 按钮按下：`transform: scale(.98)`，120ms。
- 菜单/弹出层进入：`opacity 0 → 1`，`scale(.97) translateY(2px) → 0`，160ms；退出 120ms。
- 对话框遮罩：透明度 160ms；卡片进入 260ms。
- 面板切换：位移 2px + 缩放 0.97。
- 悬停只改背景、边框、文字色，不做位移和放大。
- 所有循环动画必须在 `@media (prefers-reduced-motion: reduce)` 下停止或降级；构建产物中有 31 处相关媒体查询。

---

## 7. 布局与层级

### 7.1 断点

| 断点 | 用途 |
| --- | --- |
| `max-width: 640px` | 移动端：对话框变为底部抽屉、触控尺寸增大 |
| `max-width: 980px` | 平板/窄窗口 |
| `max-width: 1023px` | 侧栏折叠 |
| `min-width: 1024px` | 桌面布局 |
| `min-width: 1280px` / `1536px` | 宽屏 |
| `(hover: none)` | 触控设备：隐藏悬停提示、增大点击区域 |

### 7.2 关键尺寸

| Token | 值 | 用途 |
| --- | --- | --- |
| `--p-sidebar-w` | `264px` | 侧边栏 |
| `--p-content-max` | `760px` | 对话内容最大宽度 |
| `--p-content-wide` | `920px` | 宽内容 |
| `--p-table-cell-max` | `700px` | 表格单元格 |
| `--p-table-wide-max` | `1440px` | 宽表格 |
| `--p-bubble-max` | `78%` | 用户气泡最大宽度 |
| `--p-findbar-w` | `340px` | 查找栏 |
| `--p-dock-panel-h` | `320px` | Dock 面板 |
| `panel-default-w` | `460px` | 右侧面板默认宽度 |
| `panel-launcher-w` | `288px` | 面板启动器 |
| `file-tree-panel-w` | `224px`（160–400） | 文件树 |
| `--touch-target-min` | `44px` | 触控最小点击区 |
| `--resize-handle-step` | `16px` | 拖拽手柄步进 |

对话框宽度：`sm 360px`、`md 440px`、`lg 640px`、`xl 880px`；最大高度 `calc(100vh - 64px)`。移动端变为底部抽屉，高度 86dvh，仅保留顶部 16px 圆角。

### 7.3 z-index

| Token | 值 |
| --- | --- |
| `--z-base` | 0 |
| `--z-raised` | 1 |
| `--z-sticky` | 100 |
| `--z-dropdown` | 200 |
| `--z-overlay` | 300 |
| `--z-modal` | 400 |
| `--z-modal-dropdown` | 500 |
| `--z-toast` | 600 |
| `--z-tooltip` | 650 |
| `--z-max` | 9999 |

规则：不超过 650 的层级用 token；9999 只用于全屏兜底层（如 PhotoSwipe）。

---

## 8. 组件规范

### 8.1 Button

基础：`inline-flex` 居中，`gap: 8px`，`border: 0.5px solid transparent`，`font-weight: 500`，`line-height: 1`，过渡 160ms。

| 尺寸 | 高度 | 左右内边距 | 字号 | 圆角 |
| --- | --- | --- | --- | --- |
| xs | 24px | 8px | 12px | 6px |
| sm | 30px | 12px | 13px | 6px |
| md | 36px | 16px | 14px | 8px |
| lg | 42px | 20px | 15px | 12px |

变体：

| 变体 | 背景 | 文字 | 边框 | 悬停 |
| --- | --- | --- | --- | --- |
| primary | `--color-accent` | 白 | 同背景 | `--color-accent-hover` |
| secondary | `--color-surface-raised` | `--color-text` | `--color-line-strong` | 背景 `--color-hover` |
| inverted | `--color-send-bg` | `--color-send-icon` | 透明 | `--color-send-bg-hover` |
| ghost | 透明 | `--color-text-muted` | 透明 | 背景 `--color-hover`，文字 `--color-text-strong` |
| danger | `--color-danger` | 白 | 同背景 | `filter: brightness(.96)` |
| danger-soft | `--color-danger-soft` | `--color-danger` | `--color-danger-bd` | 填充为 `--color-danger` |
| orange-soft | `--color-orange-soft` | `--color-orange` | 透明 | — |
| text | 透明 | `--color-text-muted` | 透明 | 文字变 `--color-text`，下划线 |

状态：`focus-visible` 用强焦点环；`active` 缩放 0.98；`disabled` 透明度 0.5 且禁用变换；加载中内容透明度 0.7。

### 8.2 IconButton

| 尺寸 | 边长 | 圆角 | 图标 |
| --- | --- | --- | --- |
| sm | 26px | 6px | 16px |
| md | 32px | 8px | 16px |
| lg | 44px | 8px | 20px |

默认透明背景、`--color-text-muted`；悬停加 `--color-hover` 并变 `--color-text`；按下态用 `--color-selected`；焦点用普通焦点环。

### 8.3 Input

| 尺寸 | 高度 | 字号 | 圆角 | 左右内边距 |
| --- | --- | --- | --- | --- |
| xs | 24px | 13px | 6px | 8px |
| sm | 32px | 13px | 6px | 12px |
| md | 38px | 14px | 8px | 12px |

- 背景 `--color-surface-overlay`，边框 0.5px `--color-line-strong`，阴影 `--shadow-xs`。
- 占位符 `--color-text-faint`。
- 聚焦：边框 `--color-accent`，外加 `--p-focus-ring`。
- 禁用：透明度 0.5。
- 嵌入式变体（`.is-embedded`）去掉边框、背景和阴影，用于组合输入框内部。

### 8.4 Badge

| 尺寸 | 高度 | 左右内边距 | 字号 | 圆角 |
| --- | --- | --- | --- | --- |
| sm | 18px | 7px | 11px | 999px |
| md | 22px | 9px | 12px | 999px |
| lg | 自适应 | 8px | 13px | 8px |

变体：`neutral`、`soft`、`info`、`success`、`warning`、`danger`、`solid`。圆点 6px，使用 `currentColor`。状态徽标必须同时有文字，不能只靠颜色区分。

### 8.5 Banner

- 内边距 10px 14px，间距 10px，圆角 8px，字号 13px，行高 1.5。
- 默认背景 `--color-surface`，边框 `--color-line`。
- `info` / `warning` / `danger` 使用对应的 `*-soft` 背景与 `*-bd` 边框。
- 图标 18px，不参与文本换行。

### 8.6 ActionCard

- 全宽，内边距 16px，间距 12px，圆角 12px。
- 背景 `--color-surface-raised`，边框 0.5px `--color-line`。
- 悬停：边框 `--color-line-strong`，背景 `--color-surface`。
- 标题 16px/500；说明 13px，`--color-text-muted`；尾部箭头 `--color-text-faint`。
- 焦点使用强焦点环；禁用透明度 0.5。

### 8.7 Segmented Control

- 容器：`padding: 2px`，`gap: 2px`，背景 `--color-surface-sunken`，边框 `--color-line`，圆角 8px。
- 项：md 内边距 5px 12px，字号 13px；sm 高 24px；xs 高 20px。
- 选中项：背景 `--color-surface-raised`，阴影 `--shadow-sm`，文字 `--color-text`。
- 未选中文字 `--color-text-muted`，悬停变 `--color-text`。
- 支持 7px 色点（`--color-*` 用 `currentColor` 边框 0.5px）。

### 8.8 Menu

- 容器：最小宽度 180px，内边距 3.5px，圆角 12px，边框 0.5px `--color-line`，阴影 `--shadow-menu`。
- 背景：`--color-menu-bg`（白色 95% / 深色 `#292929` 95%），`backdrop-filter: blur(24px) saturate(1.8)`。
- 菜单项：内边距 5px 9px，图标间距 7px，字号 13px，字重 475，圆角 8px。
- 悬停：背景 `--color-hover`，文字 `--color-text-strong`。
- 选中：背景 `--color-hover`，文字 `--color-text`。
- 危险项：文字 `--color-danger`，图标同色。
- 大号项：最小高度 44px，内边距 12px 14px。
- 分隔线：1px `--color-line`，上下外边距 4px。
- 滚动条宽 3px，最小滑块 24px。

### 8.9 Dialog

- 遮罩：`#0d111747`，水平/垂直居中，内边距 24px。
- 面板：背景 `--color-surface-raised`，0.5px `--color-line`，圆角 16px，阴影 `--shadow-xl`，最大高度 `calc(100vh - 64px)`。
- 宽度：360 / 440 / 640 / 880px，均使用 `min(width, 100%)`。
- 头部：内边距 20px 22px 14px；标题 16px/500/1.25；描述 14px，`--color-text-muted`，上边距 4px。
- 主体：内边距 4px 22px 18px；可滚动。
- 底部：内边距 14px 22px 20px；按钮右对齐，间距 10px。
- 移动端：底部抽屉，高度 `86dvh`，顶部圆角 16px，底部安全区内边距。

### 8.10 Toast

- 宽 360px，内边距 13px 14px，间距 11px，圆角 12px，阴影 `--shadow-sm`。
- 背景 `--color-surface-raised`，边框 0.5px `--color-line`。
- 图标容器 20px 圆形，12px 图标；按状态使用 `*-soft` 背景和状态色。
- 危险 Toast 边框为 35% 危险色混合。

### 8.11 Tooltip

- 最大宽度 280px，内边距 4px 8px，圆角 6px。
- 背景 `--color-text`，文字 `--color-bg`，字号 12px，行高 1.35。
- 最多显示 `--tip-lines` 行，超出省略。
- 进入 300ms；`pointer-events: none`；层级 `--z-tooltip`。

### 8.12 Spinner

- 尺寸：xs 16px（特殊）、sm 14px、md 18px、lg 28px。
- 轨道 `--color-line`，弧线 `currentColor`，线宽 2.2，圆头。
- 旋转周期 0.7s。

### 8.13 滚动条

- 轨道不可见，滑块默认 4px，悬停/拖动 6px，命中区 10px。
- 滑块颜色 `color-mix(in srgb, var(--color-text-muted) 62%, transparent)`，悬停 82%。
- 默认透明度 0，滚动时出现；圆角 999px。
- 聊天区滚动条更细：12% 文字色，悬停 25%。

### 8.14 Composer（输入框）

- 外壳：圆角 32px，`corner-shape: superellipse(1.5)`，0.5px `--color-composer-line`，背景 `--color-composer-bg`。
- 聚焦：通过 `:after` 叠加 `--color-composer-focus-line` 边框，不改变布局。
- 内边距：7px 16px 12px；底部 Dock 场景 14px。
- 发送按钮：32px 圆形，背景 `--color-send-bg`，图标 `--color-send-icon`；悬停 `--color-send-bg-hover`。
- 附带按钮：32px 圆形，与发送按钮同尺寸。
- 展开态最大高度 70dvh。

---

## 9. 可访问性

### 9.1 焦点与触控

- 所有交互元素必须支持键盘焦点，并使用 `:focus-visible`。
- 默认焦点环：3px `--color-accent-soft`；高强调场景再加 1px `--color-accent`。
- 触控目标最小 44px；桌面图标按钮可缩小到 26/32px，但移动端需通过媒体查询放大。
- 图标按钮必须有 `aria-label`；纯图标菜单项必须有可读文本或 `aria-label`。
- 滚动区域需要可聚焦（`tabindex="0"`），并有可见焦点。

### 9.2 对比度审计

按 WCAG 2.x 相对亮度计算，关键组合如下：

| 组合 | Light | Dark | 结论 |
| --- | --- | --- | --- |
| `text` on `bg` | 19.47:1 | 15.19:1 | 通过 AAA |
| `muted` on `bg` | 7.86:1 | 8.03:1 | 通过 AAA |
| `faint` on `bg` | 4.42:1 | 5.32:1 | 亮色略低于 4.5:1 |
| 白字 on `accent` | 3.67:1 | 3.49:1 | 仅满足大文本/图形 3:1 |
| success on success-soft | 4.87:1 | 5.67:1 | 通过 AA |
| warning on warning-soft | 4.26:1 | 5.81:1 | 亮色略低于 4.5:1 |
| danger on danger-soft | 4.68:1 | 4.79:1 | 通过 AA |

使用建议：

- 主按钮白字为 14px/500 时，严格按 WCAG AA 属于不通过；若面向强合规场景，应加深强调色或把主按钮文字提升到 18.66px 粗体/24px 常规。
- `--color-text-faint` 只用于占位符、非关键提示，不要承载必读信息。
- 亮色 warning 软底上的文字接近临界值，长文本建议改用普通表面 + 深色文字。
- 不要用颜色作为唯一状态信号；成功/警告/危险必须配合图标或文字。

### 9.3 动效与主题

- 循环动画、闪烁、渐变光效在 `prefers-reduced-motion: reduce` 下关闭。
- 主题同时支持 `light` / `dark` / `system`；`system` 跟随 `prefers-color-scheme`。
- `meta name="color-scheme"` 声明为 `light dark`，确保原生控件跟随主题。

---

## 10. 实现规则

### 10.1 Do

- 一律通过 `var(--token)` 使用设计值，组件内不写死十六进制颜色。
- 新组件先复用 `--color-*`、`--space-*`、`--radius-*`、`--text-*`，确需新增时放到组件私有前缀（如 `--p-*`）。
- 暗色主题只覆盖语义 token，不复制整套组件样式。
- 边框默认 0.5px；需要更强分隔时优先加深颜色，而不是加粗到 2px。
- 浮层使用“背景 + 阴影 + 发丝线”三重分层。
- 状态切换优先 120–160ms，并使用 `--ease-out`。
- 对话框、菜单、Toast 都要有明确的进入和退出动画，退出通常比进入快。
- 桌面与移动端分别验证：移动端对话框变底部抽屉，触控目标放大。

### 10.2 Don't

- 不要用 `--color-accent` 表示成功或信息；使用对应的状态 token。
- 不要在正文中使用 600/700 字重；正文是 400，强调是 600。
- 不要用纯黑 `#000` 作为亮色主题正文（正文是 95% 黑）。
- 不要在暗色主题中复用亮色阴影；暗色阴影更黑、更重。
- 不要用 `opacity` 弱化文字层级；使用 `text-muted` / `text-faint`。
- 不要给菜单项、徽标使用 16px 大圆角；按派生圆角保持同心。
- 不要只靠颜色区分状态；必须加图标或文字。
- 不要省略 `:focus-visible` 样式，也不要用 `outline: none` 后不补焦点环。

---

## 11. 最小可用 Token 集

以下片段可直接作为新项目的基础层，数值来自生产构建：

```css
:root {
  --color-bg: #ffffff;
  --color-surface: #f5f5f5;
  --color-surface-raised: #ffffff;
  --color-surface-overlay: #ffffff;
  --color-surface-sunken: #f5f5f5;
  --color-surface-deep: #f5f5f5;
  --color-sidebar-bg: #f9fbfc;
  --color-text-strong: #000000;
  --color-text: rgba(0, 0, 0, .95);
  --color-text-muted: rgba(0, 0, 0, .68);
  --color-text-faint: rgba(0, 0, 0, .53);
  --color-line: rgba(0, 0, 0, .13);
  --color-line-strong: rgba(0, 0, 0, .15);
  --color-hover: rgba(0, 0, 0, .03);
  --color-selected: rgba(0, 0, 0, .05);
  --color-accent: #1783ff;
  --color-accent-hover: #167ff7;
  --color-accent-soft: #e8f3ff;
  --color-accent-bd: rgba(23, 131, 255, .25);
  --color-success: #0e7a38;
  --color-warning: #a9610a;
  --color-danger: #c0392b;

  --space-1: 4px;
  --space-1-5: 6px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-composer: 32px;
  --radius-full: 999px;

  --shadow-xs: 0 1px 2px rgba(16, 24, 40, .04);
  --shadow-sm: 0 1px 2px rgba(16, 24, 40, .05), 0 1px 3px rgba(16, 24, 40, .06);
  --shadow-md: 0 4px 12px rgba(16, 24, 40, .07), 0 2px 4px rgba(16, 24, 40, .05);
  --shadow-lg: 0 12px 32px rgba(16, 24, 40, .12), 0 4px 10px rgba(16, 24, 40, .08);
  --shadow-xl: 0 24px 64px rgba(16, 24, 40, .18), 0 8px 20px rgba(16, 24, 40, .1);

  --font-ui: "Schibsted Grotesk Variable", "Noto Sans SC Variable",
    "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono Variable", ui-monospace, "SF Mono", Menlo,
    Consolas, monospace;

  --text-xs: 12px;
  --text-sm: 13px;
  --text-base: 14px;
  --text-lg: 16px;
  --text-xl: 18px;
  --text-2xl: 20px;
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-prose: 1.6;
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-section-label: 600;
  --weight-semibold: 700;

  --duration-fast: .12s;
  --duration-base: .16s;
  --duration-slow: .26s;
  --ease-out: cubic-bezier(.16, 1, .3, 1);
  --ease-in-out: cubic-bezier(.4, 0, .2, 1);

  --p-hairline: .5px;
  --p-focus-ring: 0 0 0 3px var(--color-accent-soft);
  --p-focus-ring-strong: 0 0 0 3px var(--color-accent-soft),
    0 0 0 1px var(--color-accent);
}

html[data-color-scheme="dark"] {
  color-scheme: dark;
  --color-bg: #121212;
  --color-surface: #1f1f1f;
  --color-surface-raised: #292929;
  --color-surface-overlay: rgba(255, 255, 255, .1);
  --color-surface-sunken: #121212;
  --color-surface-deep: #0d0d0d;
  --color-sidebar-bg: #0d0d0d;
  --color-text-strong: #ffffff;
  --color-text: rgba(255, 255, 255, .9);
  --color-text-muted: rgba(255, 255, 255, .64);
  --color-text-faint: rgba(255, 255, 255, .5);
  --color-line: rgba(255, 255, 255, .12);
  --color-line-strong: rgba(255, 255, 255, .18);
  --color-hover: rgba(255, 255, 255, .05);
  --color-selected: rgba(255, 255, 255, .1);
  --color-accent: #1a88ff;
  --color-accent-hover: #258eff;
  --color-accent-soft: rgba(26, 136, 255, .1);
  --color-accent-bd: rgba(26, 136, 255, .28);
  --color-success: #3fb950;
  --color-warning: #d29922;
  --color-danger: #f85149;
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, .2);
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, .22), 0 1px 3px rgba(0, 0, 0, .18);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, .3), 0 2px 4px rgba(0, 0, 0, .24);
  --shadow-lg: 0 12px 32px rgba(0, 0, 0, .34), 0 4px 10px rgba(0, 0, 0, .28);
  --shadow-xl: 0 24px 64px rgba(0, 0, 0, .42), 0 8px 20px rgba(0, 0, 0, .32);
}
```

---

## 12. 解析说明与边界

| 项目 | 结果 |
| --- | --- |
| 主 CSS | 648,756 字符，单文件 |
| 根级自定义属性 | 521 个（含组件私有） |
| 暗色覆盖 | 95 个，集中在语义颜色、阴影、发送按钮 |
| class 名 | 2,758 个 |
| 主字体 | Schibsted Grotesk Variable + Noto Sans SC Variable |
| 等宽字体 | JetBrains Mono Variable |
| 图标尺寸 | 14 / 16 / 18 / 20 / 28px |
| 媒体查询 | 31 处 reduced-motion、24 处 640px、21 处 hover:none |

需要注意：

- `dist-web` 是编译产物，不包含组件 API、设计意图说明和用法文档；本文的组件规范来自 CSS 规则反推。
- 产物中同时存在新版语义 token（`--color-*`）和旧版别名（`--panel`、`--blue`、`--soft`、`--bd` 等）。新代码应只使用 `--color-*`。
- 构建哈希会随版本变化，token 名称通常稳定；引用文件时以当次 `index.html` 中的 CSS 名为准。
- 部分 token 只在特定组件块内定义（如 `--markstream-*`、`--vscode-*`），不应提升为全局设计 token。
- 未发现源地图或 Web UI 源码，因此无法确认哪些规则是死代码；本文只收录了有明确组件引用的值。

---

## 13. 群聊与多 Bot 协作界面（本仓库扩展）

> **来源说明**：本节不是 `dist-web` 的解析结果，而是本项目为「人 + 多个 Bot 同处一个会话」补充的界面规范。
> **约束**：只使用 §3–§7 已定义的 token；确需新增的尺寸以组件私有前缀 `--p-*` 定义在 `web/src/styles/tokens.css`，不进入语义层，也不新增颜色。

### 13.1 布局

| 区域 | 尺寸 | 说明 |
| --- | --- | --- |
| Bot 轨道 | `--p-rail-w`（64px） | 头像列，与侧栏以 `--color-line` 分隔 |
| 侧栏 | `--p-sidebar-w`（264px） | 群聊 / 私聊分区列表 |
| 对话内容 | 最大 `--p-content-max`（760px） | 与单聊一致，居中留白 |
| 右侧面板 | 460px（`panel-default-w`） | 参与者、记忆、产物 |

- 断点沿用 §7.1：≤1023px 侧栏折叠为抽屉；≤980px 收起右侧面板；≤640px 群设置变底部抽屉。
- 群头部高度 `--p-group-header-h`（56px），底部 0.5px `--color-line`，与单聊头部一致。

### 13.2 消息

| 元素 | 规格 |
| --- | --- |
| 作者行 | 头像 `--p-avatar-sm`（24px）+ 名字 13px / `--weight-medium` / `--color-text` + 时间 12px / `--color-text-faint` |
| 人类消息 | 气泡背景 `--color-user-bubble-bg`，圆角 `--radius-xl`，最大宽度 `--p-bubble-max`，内边距 10px 14px |
| Bot 消息 | 不用气泡，正文直接铺在 `--color-bg`；最大宽度 `--p-content-max`；身份靠头像与名字，不靠颜色 |
| 回复关系 | 消息上方一行 `↳ 回复 @名字`，12px / `--color-text-muted`；点击滚动到原消息，原消息短暂高亮 `--color-selected` |
| 系统消息 | 居中，12px / `--color-text-faint`；用于跳数上限、成员变更，不使用状态色 |
| 消息进入 | `opacity 0 → 1` + `translateY(2px) → 0`，`--duration-base`，`--ease-out` |

### 13.3 @ 提及

- 有效提及：背景 `--color-accent-soft`，文字 `--color-accent`，圆角 `--radius-xs`，左右内边距 4px，不换行。
- 非成员或不存在的提及：文字 `--color-text-muted`，无底色，悬停不变，避免给出「可点击」的错觉。
- 不能只靠颜色表达「已提及」：文本中必须保留 `@` 字符，读屏可读。

### 13.4 MentionPicker（@ 选择器）

- 复用 §8.8 Menu：最小宽度 180px、内边距 3.5px、圆角 12px、0.5px `--color-line`、`--shadow-menu`、背景 `--color-menu-bg` + `blur(24px) saturate(1.8)`。
- 行高 32px：头像 20px + 名字 13px / `--weight-option-label`（475）+ slug 12px / `--color-text-faint`。
- 悬停 `--color-hover`，键盘选中 `--color-selected`；↑↓ 循环、Enter 选中、Esc 关闭。
- 无匹配时一行 12px / `--color-text-muted`「没有匹配的 Bot」。
- ARIA：输入框 `aria-expanded` + `aria-controls`；列表 `role="listbox"`；项 `role="option"` + `aria-selected`。

### 13.5 多 Bot「正在输入」

- 位置：输入框上方一行，13px / `--color-text-muted`，例如「Coder、盯盘 正在输入」。
- 三点：`--p-typing-dot`（4px）圆点，`--color-text-faint`，周期 `--duration-flash`（1.2s），彼此错开 150ms。
- `prefers-reduced-motion: reduce` 下取消动画，只保留静态文字。
- `aria-live="polite"`；同一 Bot 的状态在 5s 内不重复播报。

### 13.6 参与者与群设置

- 头部堆叠头像：24px，重叠 -6px，外圈 2px `--color-bg`；超过 4 个显示 `+N`（§8.4 badge sm）。
- 点击参与者打开群设置，使用 §8.9 Dialog（宽度 440px）；开关项使用 §8.7 Segmented Control。
- 移除 Bot、归档群等破坏性操作：`danger-soft` 按钮 + 二次确认；确认文案写清「会话与消息将一并删除」。

### 13.7 群内审批卡片

- 复用 §8.6 ActionCard（16px 内边距、12px 圆角、`--color-surface-raised`、0.5px `--color-line`）。
- 风险分级用状态色成套：普通 `--color-surface`；写文件/执行命令用 `--color-warning-soft` + `-bd` + `--color-warning`；对外发送/删除用 `--color-danger-soft` + `-bd` + `--color-danger`。
- 标题「需要你确认」16px / 500；说明 13px / `--color-text-muted`；倒计时 12px / `--color-text-faint`。
- 按钮 36px（md）；Bot 身份不渲染按钮，只显示只读状态「等待你确认」。

### 13.8 群聊 Do / Don't

**Do**

- Bot 与人类都用「头像 + 名字」识别，颜色只做辅助。
- 每次跳数上限命中时，用系统消息说明原因与下一步（「请手动 @」）。
- 多个 Bot 同时回复时，按 `reply_to` 分组渲染，组间留 `--space-5`。
- 键盘可达：@ 选择器、消息跳转、审批按钮全部可 Tab / Enter 操作。

**Don't**

- 不要给不同 Bot 分配固定色相来区分身份——暗色对比度不可控，且违反「状态色成套」原则。
- 不要用 `--color-accent` 表示 Bot 身份或成功态。
- 不要在群聊里用「正在输入」动画超过 3 个 Bot 同时展示，多余的折叠为「+N 也在输入」。
- 不要把系统消息做成 Toast；它在会话流里，不打断用户。

### 13.9 新增组件私有 token（仅群聊）

```css
:root {
  --p-rail-w: 64px;
  --p-group-header-h: 56px;
  --p-avatar-sm: 24px;
  --p-avatar-md: 32px;
  --p-typing-dot: 4px;
  --p-mention-pad-x: 4px;
}
```

以上只允许放在 `tokens.css` 的组件私有区，不提升为全局语义 token；颜色一律复用 §3 的既有 token。
