"""Regression test: workflow_loop._attach_thinking must persist thinking.

Before the fix, _run_workflow discarded ``turn_thinking_parts`` (received from
``_run_single_agent_turn`` as ``_``). The live ThinkingDeltaEvent stream still
drove the TUI, but ``message_to_dict`` never saw ``additional_properties.thinking``
or a thinking content block, so the JSONL on disk had no ``thinking`` field and
reloading the session lost the think block.

The second iteration fixed per-turn splitting: ``thinking_groups`` is a
list-of-lists where each inner list holds the thinking deltas for the
corresponding assistant message, so the loaded transcript preserves the same
per-bubble thinking that the live stream showed.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from agent_framework._types import Content, Message

from coding_agent.session import (
    create_session,
    dict_to_message,
    load_session,
    message_to_dict,
    save_session,
)
from coding_agent.workflow_loop import _attach_thinking


@pytest.fixture(autouse=True)
def _isolate_home_and_session_dir():
    tmp = tempfile.mkdtemp()
    os.environ["HOME"] = tmp
    import coding_agent.session as s

    s._SESSIONS_DIR = Path(tmp) / ".coding-agent" / "sessions"
    yield
    shutil.rmtree(tmp)


# --- Single assistant message (no tool call) ---


def test_attach_thinking_writes_additional_properties():
    assistant = Message(role="assistant", contents=[Content(type="text", text="answer")])
    _attach_thinking([assistant], [["Let me ", "think ", "about ", "this"]])
    d = message_to_dict(assistant)
    assert d.get("thinking") == "Let me think about this"


def test_thinking_survives_disk_round_trip():
    assistant = Message(role="assistant", contents=[Content(type="text", text="answer")])
    _attach_thinking([assistant], [["Let me ", "think ", "about ", "this"]])

    session = create_session(title="t", model="m")
    session.messages = [message_to_dict(assistant)]
    sid = session.id
    save_session(session)

    loaded = load_session(sid)
    reloaded = next(m for m in loaded.messages if m["role"] == "assistant")
    assert reloaded.get("thinking") == "Let me think about this"


def test_dict_to_message_round_trip_preserves_thinking():
    assistant = Message(role="assistant", contents=[Content(type="text", text="answer")])
    _attach_thinking([assistant], [["Let me ", "think ", "about ", "this"]])

    d = message_to_dict(assistant)
    restored = dict_to_message(json.loads(json.dumps(d)))
    serialised_again = message_to_dict(restored)
    assert serialised_again.get("thinking") == "Let me think about this"


# --- Empty / edge cases ---


def test_empty_thinking_groups_is_noop():
    fresh = Message(role="assistant", contents=[Content(type="text", text="hi")])
    _attach_thinking([fresh], [])
    assert getattr(fresh, "additional_properties", None) in (None, {})


def test_empty_group_in_list_is_noop_for_that_message():
    """An empty inner list means no thinking was emitted during that turn."""
    msg1 = Message(role="assistant", contents=[Content(type="text", text="a")])
    msg2 = Message(role="assistant", contents=[Content(type="text", text="b")])
    _attach_thinking([msg1, msg2], [["thinking for msg1"], []])
    assert message_to_dict(msg1).get("thinking") == "thinking for msg1"
    assert "thinking" not in message_to_dict(msg2)


# --- Multi-assistant (tool call) splitting ---


def test_thinking_split_across_two_assistant_messages():
    """Regression: a single agent.run() may produce multiple assistant messages
    (one with function_call, one with text after the tool result). Each
    assistant message should get ONLY the thinking from its own LLM turn, not
    the combined thinking from the whole run.
    """
    first = Message(
        role="assistant",
        contents=[Content(type="function_call", call_id="c1", name="ls", arguments="{}")],
    )
    second = Message(role="assistant", contents=[Content(type="text", text="final answer")])
    _attach_thinking(
        [first, second],
        [["pre-tool thinking"], ["post-tool thinking"]],
    )

    first_dict = message_to_dict(first)
    second_dict = message_to_dict(second)
    assert first_dict.get("thinking") == "pre-tool thinking"
    assert second_dict.get("thinking") == "post-tool thinking"


def test_thinking_attached_when_first_message_is_tool():
    """If the response starts with a tool message, thinking still attaches to
    the first assistant message that follows."""
    tool = Message(role="tool", contents=[Content(type="function_result", call_id="c1", name="ls", result="x")])
    assistant = Message(role="assistant", contents=[Content(type="text", text="final")])
    _attach_thinking([tool, assistant], [["only thinking"]])
    assert message_to_dict(assistant).get("thinking") == "only thinking"
    assert message_to_dict(tool).get("role") == "tool"


def test_thinking_skipped_when_no_assistant_message_present():
    user_msg = Message(role="user", contents=[Content(type="text", text="hi")])
    tool_msg = Message(role="tool", contents=[Content(type="function_result", call_id="c1", name="ls", result="x")])
    _attach_thinking([user_msg, tool_msg], [["orphan thinking"]])
    # No assistant messages — nothing should be modified.
    assert getattr(user_msg, "additional_properties", None) in (None, {})
    assert getattr(tool_msg, "additional_properties", None) in (None, {})


def test_fewer_groups_than_assistant_messages():
    """If there are more assistant messages than groups, extra messages get no thinking."""
    msg1 = Message(role="assistant", contents=[Content(type="text", text="a")])
    msg2 = Message(role="assistant", contents=[Content(type="text", text="b")])
    msg3 = Message(role="assistant", contents=[Content(type="text", text="c")])
    _attach_thinking([msg1, msg2, msg3], [["only one group"]])
    assert message_to_dict(msg1).get("thinking") == "only one group"
    assert "thinking" not in message_to_dict(msg2)
    assert "thinking" not in message_to_dict(msg3)
