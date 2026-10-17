"""System prompt assembly for 小巧.

Builds a system prompt that tells the model its identity, capabilities,
tool interfaces, and project context.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# ── Data types ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectContext:
    """Summary of the project the agent is working in."""

    cwd: str = ""
    git_root: str | None = None
    language_hints: Sequence[str] = field(default_factory=tuple)
    ignore_patterns: Sequence[str] = field(default_factory=tuple)
    os_name: str = ""
    shell: str = ""


@dataclass(frozen=True)
class BuildSystemPromptOptions:
    """Options used to assemble the system prompt."""

    instructions: str | None = None
    persona: str = ""
    bot_name: str = ""
    memory_block: str = ""
    extra_guidelines: Sequence[str] = field(default_factory=tuple)
    project_context: ProjectContext | None = None
    skills_prompt: str = ""
    mcp_tools_prompt: str = ""
    tool_approval: dict | None = None


# ── Builder ─────────────────────────────────────────────────────


_DEFAULT_INSTRUCTIONS = """\
你是一个编程助手，在终端中运行，与用户共享工作区并协作完成目标。
你精确、安全、高效，始终保持用户对你正在进行的操作有清晰的了解。

## 身份
你是一个全栈编程助手。你通过终端与用户交互，可以执行 shell 命令、读写文件、编辑文件、搜索文件内容和列出目录。
你是用户的协作伙伴，不是被动的工具。你会主动发现潜在问题并提出改进建议。

## 自主性与持久性
- 除非用户明确要求出方案、提问或头脑风暴，否则直接实施代码修改，不要只输出方案让用户手动执行。
- 端到端完成任务：从分析到实现到验证，不要停在中间状态。不要只分析不实现，也不要只实现不验证。
- 遇到阻碍自行尝试解决。不要轻易放弃，尝试至少 2-3 种方案后再向用户求助。
- 如果发现意外的代码问题或潜在风险，主动告知用户但不要偏离当前任务。
- 不要猜测或编造答案。如果不确定，先调查再回答。

## 工具使用
- **先读文件再编辑**。用 `read_file` 检查文件内容，用 `edit_file` 精确修改。
- `edit_file` 接受 `edits` 数组，每项包含 `oldText` 和 `newText`。多处相关修改用单次调用。
- `oldText` 必须精确匹配且在文件中唯一，尽量短但保证唯一性。
- `run_command` 执行 shell 命令，检查 `exit_code` 判断是否成功。
- 搜索文件内容用 `search_files`（正则模式），按文件名查找用 `find_files`（glob 模式）。
- `list_directory` 列出目录结构。
- `write_file` 写入文件，自动创建父目录。
- `http_fetch` 发送 HTTP 请求，`web_search` 搜索网页。
- `system_notify` 发送桌面通知，`clipboard_read`/`clipboard_write` 操作剪贴板。
- `todo_write` 管理任务计划（set/add/update/read），`report_plan` 上报执行步骤，`log_task_completion` 记录完成日志。
- `ask_user_question` 向用户提问并等待回答（1-4 题，每题 2-4 选项）。
- `get_system_info` 获取系统环境信息。
- 尽可能并行化工具调用，尤其是文件读取操作。
- 能用 `run_command` 完成的简单请求直接执行。

## 编辑约束
- **默认使用 ASCII**。非 ASCII 字符仅在有明确理由且文件已使用时才引入。
- **代码注释**只在逻辑复杂时添加，不加"将值赋给变量"之类的废话。注释使用应克制。
- **不要用 Python 脚本读写文件**，优先用 `run_command` 或 `edit_file`。
- 保持代码风格与现有代码库一致。改动最小化，只改与任务相关的部分。
- 修复问题时优先找根因，而不是打补丁。
- 不要修复与任务无关的 bug 或失败的测试。
- 不要添加内联注释，除非用户明确要求。
- 不要使用单字母变量名，除非用户明确要求。
- 不要添加版权或许可证头，除非明确要求。

## Git 安全
- 工作区可能有未提交的改动。**不要回退用户未要求修改的内容**。
- 如果有不相关的改动，不要回退它们。如果改动在你最近接触的文件中，仔细理解后配合使用。
- **禁止** `git reset --hard`、`git checkout --` 等破坏性命令，除非用户明确要求。
- 不要 `amend` commit，除非明确要求。
- 不要自动 `git commit` 或创建新分支，除非明确要求。
- 偏好非交互式 git 命令。
- 遇到意外改动立即停止并询问用户。

## 输出规范
- 用 GitHub 风格 Markdown 格式化。复杂度匹配任务：简单任务一句话，复杂任务先方案后细节。
- **不要用嵌套列表**，保持单层。需要层级时拆分成多个列表或段落。
- 标题可选，仅在必要时使用。使用短标题（1-3 词），加粗格式。
- 用反引号标注命令、路径、环境变量、代码标识符。
- 代码片段用围栏代码块，尽量包含语言标识。
- **不要用 emoji**。
- **不要说"保存/复制这个文件"**——用户和你在同一台机器上。
- **不要以"好的"、"完成了"、"好问题"等寒暄开头**。直接进入正题。
- 文件引用格式：`src/app.ts:42`（路径:行号）。使用内联代码使其可点击。
- 给出自然的后续建议（测试、提交、构建），没有就不提。多个选项时用数字列表。
- 用户看不到命令执行输出。被要求展示命令输出时，转述关键细节。
- 简单确认不需要格式化，直接用句子回答。

## 进度更新
- 在执行过程中保持与用户的沟通，每完成一个有意义的步骤时简短更新。
- 长时间操作前告知用户你在做什么。
- 更新要简洁（1-2 句话），说明当前进展和下一步。

## 代码审查
当用户要求审查时，切换到代码审查模式：
- 优先识别 bug、风险、行为回归和缺失的测试。
- 按严重性排序，附带文件:行号引用。
- 开放问题和假设跟在发现之后。
- 如果没有发现问题，明确说明并指出残留风险或测试缺口。

## 前端任务
做前端设计时，避免落入"AI 风格"或平庸的布局：
- 字体：使用有表现力的字体，避免默认字体栈（Inter、Roboto、Arial）。
- 色彩：选择明确的视觉方向，定义 CSS 变量，避免紫色默认配色。
- 动效：使用有意义的动画，而非泛泛的微交互。
- 背景：不要只用纯色背景，使用渐变、形状或纹理构建氛围。
- 整体：避免模板化布局，变化主题和视觉语言。
- 确保桌面端和移动端正常加载。
- 如果在现有设计系统内工作，保留已有的模式和风格。

## 特殊请求
- 简单请求（如查看时间）直接用终端命令执行。
- 不要尝试测试你无法测试的东西。
- 更新文档（如有必要）。
- 使用 `git log` 和 `git blame` 搜索历史获取上下文。

## 代码修改准则
- 修复问题找根因，而非表面修补。
- 避免不必要的复杂度。
- 不要尝试修复不相关的 bug。
- 保持与现有代码库风格一致。
- 改动最小化且聚焦于任务。
- 如果从零构建 Web 应用，确保有美观现代的 UI 和最佳实践。

## 验证策略
- 完成修改后考虑运行测试、lint 或构建来验证。
- 从修改涉及的具体代码开始验证，逐步扩展到更广的测试。
- 不要修复不相关的 bug。
- 格式化问题可迭代最多 3 次，仍无法解决则在最终消息中说明。
- 代码库没有配置格式化工具时不要添加。

涉及写入文件、执行 shell、修改文件前必须调用对应工具。
最后给出简短总结，说明你做了什么以及为什么。
"""


def build_system_prompt(options: BuildSystemPromptOptions) -> str:
    """Build the system prompt string."""
    parts: list[str] = []

    # Core instructions
    parts.append(options.instructions or _DEFAULT_INSTRUCTIONS)

    # Persona (SOUL.md content) sits on top of the shared contract.
    persona = options.persona.strip()
    if persona:
        name = options.bot_name.strip() or "助理"
        parts.append(f"## 人格：{name}\n{persona}")

    # Long-term memory (facts + related notes), already budgeted by the caller.
    memory = options.memory_block.strip()
    if memory:
        parts.append(memory)

    # Current date
    today = date.today()
    parts.append(f"## 当前日期\n- 今天是 {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})")

    # Extra guidelines
    if options.extra_guidelines:
        parts.append("## Additional Guidelines\n" + "\n".join(f"- {g}" for g in options.extra_guidelines))

    # Skills
    if options.skills_prompt:
        parts.append(options.skills_prompt)

    # MCP tools
    if options.mcp_tools_prompt:
        parts.append(options.mcp_tools_prompt)

    # Project context
    ctx = options.project_context
    if ctx and ctx.cwd:
        ctx_lines = [f"- Working directory: `{ctx.cwd}`"]
        if ctx.git_root:
            ctx_lines.append(f"- Git root: `{ctx.git_root}`")
        if ctx.language_hints:
            ctx_lines.append(f"- Languages detected: {', '.join(ctx.language_hints)}")
        if ctx.ignore_patterns:
            ctx_lines.append("- Ignored patterns: " + ", ".join(ctx.ignore_patterns[:5]))
        if ctx.os_name:
            ctx_lines.append(f"- OS: {ctx.os_name}")
        if ctx.shell:
            ctx_lines.append(f"- Shell: {ctx.shell}")
        parts.append("## Project Context\n" + "\n".join(ctx_lines))

    # OS-specific shell guidance
    if ctx and ctx.os_name and "Windows" in ctx.os_name:
        parts.append(
            "## Windows Shell Guidance\n"
            "- Prefer PowerShell commands. The `run_command` tool runs via `pwsh -NoProfile -Command <cmd>`.\n"
            "- Avoid Unix-only syntax (e.g. `ls`, `grep`, `cat`, `sed`, single quotes for paths).\n"
            "- Use Windows-compatible paths and commands when possible."
        )

    # Dynamic tool approval info
    if options.tool_approval:
        approval = options.tool_approval
        if approval.get("enabled", True):
            always = approval.get("always_require", [])
            never = approval.get("never_require", [])
            if always:
                tools_str = "、".join(f"`{t}`" for t in always)
                parts.append(f"## Tool Approval\n- 需要用户审批的工具：{tools_str}")
            if never:
                never_str = "、".join(f"`{t}`" for t in never)
                parts.append(f"- 无需审批的工具：{never_str}")

    return "\n\n".join(parts)


def _detect_shell() -> str:
    """Return a human-readable shell name for the current OS."""
    if sys.platform == "win32":
        return "PowerShell (pwsh)"
    shell = os.environ.get("SHELL", "")
    if shell:
        return Path(shell).name
    return "bash"


def discover_project_context(cwd: str | None = None) -> ProjectContext:
    """Gather project context from the current working directory."""
    root = Path(cwd or Path.cwd()).resolve()

    git_root = None
    git_dir = root
    for _ in range(10):
        if (git_dir / ".git").exists():
            git_root = str(git_dir)
            break
        parent = git_dir.parent
        if parent == git_dir:
            break
        git_dir = parent

    # Detect language hints from common config files
    hints: list[str] = []
    for marker, lang in [
        ("pyproject.toml", "Python"),
        ("package.json", "JavaScript/TypeScript"),
        ("Cargo.toml", "Rust"),
        ("go.mod", "Go"),
        ("Gemfile", "Ruby"),
        ("Makefile", "Make"),
        ("CMakeLists.txt", "CMake"),
        ("pom.xml", "Java"),
        ("build.gradle", "Gradle"),
    ]:
        if (root / marker).exists():
            hints.append(lang)

    # Gitignore patterns
    ignore: list[str] = []
    gitignore_path = (git_dir or root) / ".gitignore"
    if gitignore_path.exists():
        for line in gitignore_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                ignore.append(line)

    os_name = f"{platform.system()} {platform.release()}".strip()
    shell = _detect_shell()
    logger.info("Detected OS: %s, shell: %s", os_name, shell)
    return ProjectContext(
        cwd=str(root),
        git_root=git_root,
        language_hints=hints,
        ignore_patterns=ignore[:20],
        os_name=os_name,
        shell=shell,
    )
