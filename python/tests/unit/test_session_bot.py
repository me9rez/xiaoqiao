"""Bot ownership survives the JSONL session round-trip."""

from __future__ import annotations

from pathlib import Path

from xiaoqiao import session


def test_bot_id_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session, "_SESSIONS_DIR", tmp_path)

    created = session.create_session(title="Hello", model="deepseek/deepseek-v4-flash", bot_id="bot_1")
    session.save_session(created)

    loaded = session.load_session(created.id)
    assert loaded is not None
    assert loaded.bot_id == "bot_1"

    listed = session.list_sessions()
    assert len(listed) == 1
    assert listed[0].bot_id == "bot_1"


def test_legacy_session_without_bot_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(session, "_SESSIONS_DIR", tmp_path)

    created = session.create_session(title="Legacy")
    session.save_session(created)

    loaded = session.load_session(created.id)
    assert loaded is not None
    assert loaded.bot_id == ""
