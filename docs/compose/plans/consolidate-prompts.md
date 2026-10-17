# Plan: 合并重复的系统提示词

## 目标
将 `workflow_loop.py` 中硬编码的中文指令合并到 `system_prompt.py`，消除职责重叠。

## 背景
- `system_prompt.py` 的 `_DEFAULT_INSTRUCTIONS` 包含英文基础指令
- `workflow_loop.py` 第 338-342 行追加了中文角色指令
- 两者语义重叠：先分析 → 调用工具 → 给总结

## 任务

### T1: 合并中文指令到 system_prompt.py
- 在 `_DEFAULT_INSTRUCTIONS` 中追加中文角色指令
- 保持原有英文 guidelines 不变

### T2: 移除 workflow_loop.py 中的硬编码追加
- 删除第 338-342 行的 `instructions +=` 逻辑
- 改为直接使用传入的 `system_prompt`

### T3: 验证
- 运行 `cd python && uv run pytest` 确认测试通过
- 运行 `cd python && ruff check src/` 确认 lint 通过

## 关键文件
- `python/src/xiaoqiao/system_prompt.py`
- `python/src/xiaoqiao/workflow_loop.py`
