"""Unit tests for @ mention routing and hop limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from xiaoqiao.bots import Bot
from xiaoqiao.router import HopPolicy, can_trigger, filter_triggerable, parse_mentions, resolve_recipients


def _bot(bot_id: str, name: str, slug: str) -> Bot:
    return Bot(
        id=bot_id,
        name=name,
        slug=slug,
        emoji="🤖",
        persona="",
        model="",
        tools=(),
        workspace="",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


CODER = _bot("bot_coder", "Coder", "coder")
WATCH = _bot("bot_watch", "盯盘", "watch")
LIFE = _bot("bot_life", "生活助理", "life")
BOTS = [CODER, WATCH, LIFE]


class TestParseMentions:
    def test_slug(self) -> None:
        recipients, all_flag, unknown = parse_mentions("@coder 看一下", BOTS)
        assert recipients == ["bot_coder"]
        assert all_flag is False
        assert unknown == []

    def test_display_name(self) -> None:
        recipients, _, _ = parse_mentions("@盯盘 查行情", BOTS)
        assert recipients == ["bot_watch"]

    def test_multiple_and_dedupe(self) -> None:
        recipients, _, _ = parse_mentions("@coder @watch @coder", BOTS)
        assert recipients == ["bot_coder", "bot_watch"]

    def test_all_flag(self) -> None:
        _, all_flag, _ = parse_mentions("@all 开会", BOTS)
        assert all_flag is True

    def test_unknown(self) -> None:
        recipients, _, unknown = parse_mentions("@nobody hi @coder", BOTS)
        assert recipients == ["bot_coder"]
        assert unknown == ["nobody"]


class TestResolveRecipients:
    def test_mention(self) -> None:
        decision = resolve_recipients("@watch 查行情", BOTS, CODER.id)
        assert decision.recipients == ("bot_watch",)
        assert decision.reason == "mention"

    def test_all_is_capped(self) -> None:
        decision = resolve_recipients("@all 开工", BOTS, CODER.id, max_bots=2)
        assert decision.recipients == ("bot_coder", "bot_watch")
        assert decision.reason == "all"
        assert decision.truncated is True

    def test_default_when_no_mention(self) -> None:
        decision = resolve_recipients("大家好", BOTS, default_bot_id=LIFE.id)
        assert decision.recipients == ("bot_life",)
        assert decision.reason == "default"

    def test_first_bot_when_no_default(self) -> None:
        decision = resolve_recipients("hi", BOTS)
        assert decision.recipients == ("bot_coder",)
        assert decision.reason == "default"

    def test_unknown_mention_falls_back(self) -> None:
        decision = resolve_recipients("@ghost hi", BOTS, default_bot_id=WATCH.id)
        assert decision.recipients == ("bot_watch",)
        assert decision.reason == "fallback"
        assert decision.unknown == ("ghost",)

    def test_empty_group(self) -> None:
        decision = resolve_recipients("@coder hi", [])
        assert decision.recipients == ()
        assert decision.reason == "empty"


class TestHopPolicy:
    def test_allows_first_hop(self) -> None:
        ok, reason = can_trigger(hop=0, bot_id="bot_a")
        assert (ok, reason) == (True, "allowed")

    def test_blocks_beyond_max_hops(self) -> None:
        ok, reason = can_trigger(hop=4, bot_id="bot_a", policy=HopPolicy(max_hops=3))
        assert (ok, reason) == (False, "hop_limit")

    def test_blocks_self_repeat(self) -> None:
        ok, reason = can_trigger(hop=1, bot_id="bot_a", last_speaker_id="bot_a")
        assert (ok, reason) == (False, "self_repeat")

    def test_blocks_within_cooldown(self) -> None:
        now = datetime.now(UTC)
        ok, reason = can_trigger(
            hop=1,
            bot_id="bot_a",
            last_run_at=now - timedelta(seconds=1),
            now=now,
            policy=HopPolicy(cooldown_seconds=2),
        )
        assert (ok, reason) == (False, "cooldown")

    def test_allows_after_cooldown(self) -> None:
        now = datetime.now(UTC)
        ok, _ = can_trigger(
            hop=1,
            bot_id="bot_a",
            last_run_at=now - timedelta(seconds=5),
            now=now,
        )
        assert ok is True

    def test_filter_triggerable(self) -> None:
        now = datetime.now(UTC)
        allowed, rejected = filter_triggerable(
            ["bot_a", "bot_b"],
            hop=1,
            last_speaker_id="bot_a",
            last_run_at={"bot_b": now},
            now=now,
        )
        assert allowed == []
        assert rejected == {"bot_a": "self_repeat", "bot_b": "cooldown"}
