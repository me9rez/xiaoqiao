# 小巧（Xiaoqiao）

一个轻量、可自托管的编程助手，既能在终端运行，也能在浏览器中使用。告诉它你想做什么，它会读取文件、执行命令、修改代码、搜索项目，并实时展示每一步的思考过程。

![初始界面](docs/assets/screenshots/empty-state.png)

## 为什么选择小巧？

- **🔧 真工具、真执行** — 支持 `bash`、文件读写/精确编辑、代码搜索，还能加载项目级 Skill。
- **⚡ 流式、可解释** — 实时看到模型的思考链、工具调用和命令输出。
- **🖥️ 简洁的 Web 界面** — 一条命令同时启动网关和前端，无需单独的终端客户端。
- **💾 会话持久化** — 对话以 JSONL 保存在本地，随时回到之前的状态。
- **🔒 本地运行** — API key 只留在你的机器上，所有数据本地处理。

![对话界面](docs/assets/screenshots/chat-session.png)

## 快速开始

### 安装

```bash
uv tool install xiaoqiao
```

> 需要 Python 3.14+。如果还没有 `uv`，可从 [astral.sh/uv](https://astral.sh/uv) 安装。

### 配置

创建 `~/.xiaoqiao/settings.json`：

```json
{
  "selectedModel": "deepseek/deepseek-v4-flash",
  "providers": {
    "deepseek": {
      "baseUrl": "https://api.deepseek.com/v1",
      "apiKey": "sk-xxx",
      "models": [
        {
          "id": "deepseek-v4-flash",
          "name": "DeepSeek V4 Flash",
          "contextWindow": 1000000,
          "maxTokens": 384000
        }
      ]
    }
  },
  "max_turns": 25
}
```

### 运行

```bash
xiaoqiao --web
```

打开 [http://127.0.0.1:8766](http://127.0.0.1:8766)，开始对话。

## 内置工具

| 工具 | 说明 |
|------|------|
| `bash` | 执行 shell 命令并捕获输出 |
| `read` | 读取项目中的任意文件 |
| `write` | 创建或覆盖文件 |
| `edit` | 精确的文本替换 |
| `search` | 使用正则递归搜索文件内容 |
| `list_dir` | 列出目录内容 |
| `load_skill` | 从 `SKILL.md` 加载用户或项目级技能 |

## 开发

想参与开发或二次定制？请参阅 [docs/development.zh.md](docs/development.zh.md) 了解架构、本地运行方式和打包流程。

## 文档

- [产品文档](docs/product.md) — 从编程助手到自托管个人 Agent
- [改造方案](docs/pivot-plan.md) — 多 Bot 运行时、数据模型与迁移
- [设计规范](docs/design.md) — token、组件、动效与可访问性
- [开发指南](docs/development.zh.md)
- [网关协议](docs/protocol.zh.md)
- [原始方案](docs/proposal.md)

## 许可证

MIT
