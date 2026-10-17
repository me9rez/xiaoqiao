"""Unit tests for the skills provider integration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, cast

import pytest

from xiaoqiao.skills import create_skills_provider


class TestCreateSkillsProvider:
    def test_create_skills_provider_with_empty_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = create_skills_provider([tmp])
            from agent_framework._skills import SkillsProvider

            assert isinstance(provider, SkillsProvider)

    @pytest.mark.asyncio
    async def test_create_skills_provider_discovers_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: test-skill\ndescription: Test Skill\n---\n\n# Test Skill\n\nThis is a test skill.",
                encoding="utf-8",
            )

            provider = create_skills_provider([tmp])
            # agent-framework >= 1.10 requires a SkillsSourceContext argument.
            from agent_framework._skills import SkillsSourceContext

            context = SkillsSourceContext(agent=cast("Any", object()))
            skills = await provider._source.get_skills(context)
            assert len(skills) == 1
            assert skills[0].frontmatter.name == "test-skill"

    def test_default_skill_dirs(self) -> None:
        provider = create_skills_provider()
        from agent_framework._skills import SkillsProvider

        assert isinstance(provider, SkillsProvider)
