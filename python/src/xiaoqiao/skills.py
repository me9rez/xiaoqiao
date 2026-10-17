"""Skills system — progressive skill loading from SKILL.md files.

Uses the agent-framework ``SkillsProvider`` so that discovered skills are
advertised via the agent's context providers and loaded through the framework's
built-in ``load_skill`` tool.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from xiaoqiao.paths import config_dir

if TYPE_CHECKING:
    from collections.abc import Sequence

    from agent_framework._skills import SkillsProvider

logger = logging.getLogger(__name__)


DEFAULT_SKILL_DIRS: Sequence[str | Path] = [
    Path.cwd() / "skills",
    config_dir() / "skills",
    Path.home() / ".agents" / "skills",
]

# Skill source classification
_BUILTIN_DIRS: set[Path] = {
    Path.cwd() / "skills",
    config_dir() / "skills",
}
_MINE_DIR: Path = Path.home() / ".agents" / "skills"


def _get_skill_source(skill_path: Path) -> str:
    """Determine skill source based on directory."""
    resolved = skill_path.resolve()
    for d in _BUILTIN_DIRS:
        try:
            resolved.relative_to(d.resolve())
            return "builtin"
        except ValueError:
            continue
    return "mine"


def _extract_description(content: str) -> str:
    """Extract description from SKILL.md content."""
    lines = content.strip().split("\n")
    for line in lines[:20]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:200]
    return ""


def create_skills_provider(
    skill_dirs: Sequence[str | Path] | None = None,
) -> SkillsProvider:
    """Create a ``SkillsProvider`` from the configured skill directories.

    Parameters
    ----------
    skill_dirs:
        Directories to scan for ``SKILL.md`` files. Defaults to the project-level
        ``./skills`` directory and the user-level ``~/.xiaoqiao/skills``.

    Returns
    -------
    A configured ``SkillsProvider`` that advertises skills and exposes the
    ``load_skill`` / ``read_skill_resource`` tools.
    """
    from agent_framework._skills import SkillsProvider

    dirs = skill_dirs if skill_dirs is not None else DEFAULT_SKILL_DIRS
    return SkillsProvider.from_paths(dirs)


def list_skills() -> list[dict[str, Any]]:
    """List all skills from configured directories.

    Returns
    -------
    List of skill info dicts with name, source, description, enabled, path.
    """
    skills: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for skill_dir in DEFAULT_SKILL_DIRS:
        dir_path = Path(skill_dir)
        if not dir_path.is_dir():
            continue

        for skill_file in dir_path.glob("*/SKILL.md"):
            skill_name = skill_file.parent.name
            if skill_name in seen_names:
                continue
            seen_names.add(skill_name)

            # Check if skill is enabled (disabled by renaming extension)
            enabled = True
            content = ""
            try:
                content = skill_file.read_text(encoding="utf-8")
            except Exception:
                pass

            skills.append(
                {
                    "name": skill_name,
                    "source": _get_skill_source(skill_file.parent),
                    "description": _extract_description(content),
                    "enabled": enabled,
                    "path": str(skill_file.parent),
                }
            )

    return skills


def get_skill(name: str) -> dict[str, Any] | None:
    """Get skill detail including SKILL.md content.

    Parameters
    ----------
    name:
        Skill name (directory name).

    Returns
    -------
    Skill info dict with content, or None if not found.
    """
    for skill_dir in DEFAULT_SKILL_DIRS:
        skill_path = Path(skill_dir) / name / "SKILL.md"
        if skill_path.is_file():
            content = skill_path.read_text(encoding="utf-8")
            return {
                "name": name,
                "source": _get_skill_source(skill_path.parent),
                "description": _extract_description(content),
                "enabled": True,
                "path": str(skill_path.parent),
                "content": content,
            }
    return None


def _build_file_tree(directory: Path, base_path: Path) -> list[dict[str, Any]]:
    """Build a file tree structure from a directory."""
    items: list[dict[str, Any]] = []
    try:
        for item in sorted(directory.iterdir()):
            rel_path = item.relative_to(base_path)
            if item.is_dir():
                children = _build_file_tree(item, base_path)
                items.append(
                    {
                        "name": item.name,
                        "type": "directory",
                        "path": str(rel_path),
                        "children": children,
                    }
                )
            else:
                items.append(
                    {
                        "name": item.name,
                        "type": "file",
                        "path": str(rel_path),
                    }
                )
    except PermissionError:
        pass
    return items


def get_skill_files(name: str) -> list[dict[str, Any]] | None:
    """Get the file tree of a skill directory.

    Parameters
    ----------
    name:
        Skill name (directory name).

    Returns
    -------
    List of file/directory items, or None if skill not found.
    """
    for skill_dir in DEFAULT_SKILL_DIRS:
        skill_path = Path(skill_dir) / name
        if skill_path.is_dir():
            return _build_file_tree(skill_path, skill_path)
    return None


def get_skill_file_content(name: str, file_path: str) -> str | None:
    """Read the content of a file in a skill directory.

    Parameters
    ----------
    name:
        Skill name (directory name).
    file_path:
        Relative path to the file within the skill directory.

    Returns
    -------
    File content as string, or None if not found.
    """
    for skill_dir in DEFAULT_SKILL_DIRS:
        skill_path = Path(skill_dir) / name / file_path
        if skill_path.is_file():
            try:
                return skill_path.read_text(encoding="utf-8")
            except Exception:
                return None
    return None


def install_skill(name: str, source_dir: str | None = None) -> dict[str, Any]:
    """Install a skill by copying to the mine directory.

    Parameters
    ----------
    name:
        Skill name to install.
    source_dir:
        Source directory containing the skill. If None, searches builtin dirs.

    Returns
    -------
    Installed skill info.
    """
    _MINE_DIR.mkdir(parents=True, exist_ok=True)

    if source_dir:
        src = Path(source_dir) / name
    else:
        src = None
        for skill_dir in _BUILTIN_DIRS:
            candidate = Path(skill_dir) / name
            if candidate.is_dir():
                src = candidate
                break

    if src is None or not src.is_dir():
        raise FileNotFoundError(f"Skill '{name}' not found in any source directory")

    dst = _MINE_DIR / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    return get_skill(name) or {"name": name, "source": "mine", "path": str(dst)}


def uninstall_skill(name: str) -> bool:
    """Uninstall a skill from the mine directory.

    Parameters
    ----------
    name:
        Skill name to uninstall.

    Returns
    -------
    True if uninstalled, False if not found.
    """
    skill_path = _MINE_DIR / name
    if skill_path.is_dir():
        shutil.rmtree(skill_path)
        return True
    return False


def toggle_skill(name: str, enabled: bool) -> bool:
    """Enable or disable a skill by renaming its SKILL.md file.

    Parameters
    ----------
    name:
        Skill name.
    enabled:
        True to enable, False to disable.

    Returns
    -------
    True if toggled, False if not found.
    """
    for skill_dir in DEFAULT_SKILL_DIRS:
        skill_path = Path(skill_dir) / name
        if skill_path.is_dir():
            skill_md = skill_path / "SKILL.md"
            skill_md_disabled = skill_path / "SKILL.md.disabled"

            if enabled and skill_md_disabled.exists():
                skill_md_disabled.rename(skill_md)
                return True
            elif not enabled and skill_md.exists():
                skill_md.rename(skill_md_disabled)
                return True
            return False
    return False


def update_skill(name: str, content: str) -> bool:
    """Update a skill's SKILL.md content.

    Parameters
    ----------
    name:
        Skill name.
    content:
        New SKILL.md content.

    Returns
    -------
    True if updated, False if not found.
    """
    for skill_dir in DEFAULT_SKILL_DIRS:
        skill_path = Path(skill_dir) / name / "SKILL.md"
        if skill_path.is_file():
            skill_path.write_text(content, encoding="utf-8")
            return True
    return False
