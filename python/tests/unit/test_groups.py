"""Unit tests for group chat membership and settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaoqiao import store
from xiaoqiao.bots import BotRepository
from xiaoqiao.groups import DEFAULT_SETTINGS, GroupRepository


@pytest.fixture
def repos(tmp_path: Path) -> tuple[BotRepository, GroupRepository]:
    db = tmp_path / "agent.db"
    return BotRepository(db), GroupRepository(db)


class TestGroupCrud:
    def test_create_and_get(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        watch = bots.create("Watch")

        group = groups.create("Daily", [coder.id, watch.id], default_bot_id=watch.id)

        assert group.name == "Daily"
        assert group.default_bot_id == watch.id
        assert group.bot_ids == (coder.id, watch.id)
        assert group.settings == DEFAULT_SETTINGS
        assert groups.get(group.id) == group

    def test_records_owner_membership(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        group = groups.create("Daily", [coder.id])

        with store.connect(groups._path) as conn:
            members = conn.execute(
                "SELECT member_type, member_id FROM group_members WHERE group_id = ?",
                (group.id,),
            ).fetchall()

        assert {(row["member_type"], row["member_id"]) for row in members} == {
            ("user", "owner"),
            ("bot", coder.id),
        }

    def test_requires_a_bot(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        _, groups = repos
        with pytest.raises(ValueError):
            groups.create("Empty", [])

    def test_rejects_unknown_bot(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        _, groups = repos
        with pytest.raises(ValueError, match="unknown bot"):
            groups.create("Bad", ["bot_missing"])

    def test_default_must_be_member(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        outsider = bots.create("Outsider")
        with pytest.raises(ValueError, match="default bot"):
            groups.create("Bad", [coder.id], default_bot_id=outsider.id)

    def test_settings_merge(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        group = groups.create("Daily", [coder.id], settings={"maxHops": 1})
        assert group.settings["maxHops"] == 1
        assert group.settings["maxBotsPerTurn"] == DEFAULT_SETTINGS["maxBotsPerTurn"]

    def test_update_and_archive(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        group = groups.create("Daily", [coder.id])

        updated = groups.update(group.id, name="Weekly", archived=True)
        assert updated is not None
        assert updated.name == "Weekly"
        assert updated.archived is True
        assert groups.list() == []


class TestMembership:
    def test_add_and_remove_bot(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        watch = bots.create("Watch")
        group = groups.create("Daily", [coder.id])

        with_watch = groups.add_bot(group.id, watch.id)
        assert with_watch is not None
        assert set(with_watch.bot_ids) == {coder.id, watch.id}

        without = groups.remove_bot(group.id, watch.id)
        assert without is not None
        assert without.bot_ids == (coder.id,)

    def test_removing_default_promotes_another(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        first = bots.create("First")
        second = bots.create("Second")
        group = groups.create("Daily", [first.id, second.id], default_bot_id=first.id)

        updated = groups.remove_bot(group.id, first.id)
        assert updated is not None
        assert updated.default_bot_id == second.id

    def test_delete_cascades_members(self, repos: tuple[BotRepository, GroupRepository]) -> None:
        bots, groups = repos
        coder = bots.create("Coder")
        group = groups.create("Daily", [coder.id])

        assert groups.delete(group.id) is True
        with store.connect(groups._path) as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM group_members WHERE group_id = ?", (group.id,)
            ).fetchone()["n"]
        assert remaining == 0
