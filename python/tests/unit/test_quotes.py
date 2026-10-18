"""Tests for attaching a quoted reply to the stored user message."""

from __future__ import annotations

from typing import Any

from xiaoqiao.runtime.quotes import MAX_QUOTE_CHARS, attach_quote, quote_param


class TestQuoteParam:
    def test_normalises_an_rpc_payload(self) -> None:
        assert quote_param({"authorName": " Coder ", "text": " hi "}) == {
            "authorName": "Coder",
            "text": "hi",
        }

    def test_truncates_long_text(self) -> None:
        quote = quote_param({"authorName": "Coder", "text": "x" * 500})

        assert quote is not None
        assert len(quote["text"]) == MAX_QUOTE_CHARS

    def test_rejects_empty_and_non_dict(self) -> None:
        assert quote_param(None) is None
        assert quote_param("nope") is None
        assert quote_param({}) is None
        assert quote_param({"authorName": "", "text": "   "}) is None

    def test_falls_back_to_a_placeholder_author(self) -> None:
        assert quote_param({"text": "hi"}) == {"authorName": "未署名", "text": "hi"}


class TestAttachQuote:
    def test_attaches_to_the_last_user_message(self) -> None:
        messages = [
            {"role": "user", "contents": [], "additional_properties": {"quoted": {"text": "old"}}},
            {"role": "assistant", "contents": []},
            {"role": "user", "contents": []},
        ]

        assert attach_quote(messages, {"authorName": "Coder", "text": "hi"}) is True
        # The new turn wins; the earlier quote is untouched.
        assert messages[2]["additional_properties"]["quoted"] == {"authorName": "Coder", "text": "hi"}
        assert messages[0]["additional_properties"]["quoted"] == {"text": "old"}

    def test_creates_the_bag_when_missing(self) -> None:
        messages = [{"role": "user", "contents": []}]

        attach_quote(messages, {"authorName": "Coder", "text": "hi"})

        assert messages[0]["additional_properties"] == {"quoted": {"authorName": "Coder", "text": "hi"}}

    def test_does_not_mutate_the_quote_it_was_given(self) -> None:
        quote = {"authorName": "Coder", "text": "hi"}
        messages: list[dict[str, Any]] = [{"role": "user"}]

        attach_quote(messages, quote)
        quote["text"] = "changed"

        properties = messages[0]["additional_properties"]
        assert isinstance(properties, dict)
        stored = properties["quoted"]
        assert isinstance(stored, dict)
        assert stored["text"] == "hi"

    def test_reports_when_there_is_no_user_message(self) -> None:
        assert attach_quote([{"role": "assistant"}], {"authorName": "Coder", "text": "hi"}) is False
        assert attach_quote([], {"authorName": "Coder", "text": "hi"}) is False
