"""Unit tests for persona injection into the system prompt."""

from __future__ import annotations

from xiaoqiao.system_prompt import BuildSystemPromptOptions, build_system_prompt


class TestPersona:
    def test_persona_is_injected(self) -> None:
        prompt = build_system_prompt(
            BuildSystemPromptOptions(persona="你说话简短，像一个靠谱的朋友。", bot_name="Coder")
        )
        assert "## 人格：Coder" in prompt
        assert "你说话简短，像一个靠谱的朋友。" in prompt

    def test_empty_persona_adds_no_block(self) -> None:
        prompt = build_system_prompt(BuildSystemPromptOptions())
        assert "## 人格" not in prompt

    def test_persona_keeps_base_contract(self) -> None:
        prompt = build_system_prompt(BuildSystemPromptOptions(persona="只做数据分析。"))
        assert "工具使用" in prompt
        assert "只做数据分析。" in prompt

    def test_persona_falls_back_to_generic_name(self) -> None:
        prompt = build_system_prompt(BuildSystemPromptOptions(persona="   "))
        assert "## 人格" not in prompt
        named = build_system_prompt(BuildSystemPromptOptions(persona="友好一点"))
        assert "## 人格：助理" in named
