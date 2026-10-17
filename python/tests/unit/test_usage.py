"""Unit tests for usage accounting and daily budgets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xiaoqiao.bots import BotRepository
from xiaoqiao.runtime.usage import UsageRepository, budget_exceeded


@pytest.fixture
def env(tmp_path: Path) -> tuple[UsageRepository, str]:
    db = tmp_path / "agent.db"
    bot = BotRepository(db).create("Coder")
    return UsageRepository(db), bot.id


class TestUsageRepository:
    def test_records_and_summarizes(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        usage.record(bot_id, "deepseek/v4", input_tokens=100, output_tokens=40)

        summary = usage.summary()

        assert summary.input_tokens == 100
        assert summary.output_tokens == 40
        assert summary.total_tokens == 140
        assert summary.runs == 1

    def test_links_to_a_real_run(self, env: tuple[UsageRepository, str], tmp_path: Path) -> None:
        from xiaoqiao.runtime.runs import RunRepository

        usage, bot_id = env
        run_id = RunRepository(tmp_path / "agent.db").begin(bot_id, trigger="web")

        entry = usage.record(bot_id, "m", run_id=run_id, input_tokens=10)

        assert entry.run_id == run_id

    def test_scoped_by_bot(self, env: tuple[UsageRepository, str], tmp_path: Path) -> None:
        usage, bot_id = env
        other = BotRepository(tmp_path / "agent.db").create("Other")
        usage.record(other.id, "m", input_tokens=10)

        assert usage.summary(bot_id=bot_id).total_tokens == 0
        assert usage.summary(bot_id=other.id).total_tokens == 10

    def test_today_ignores_old_entries(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        entry = usage.record(bot_id, "m", input_tokens=10)
        # Backdate the row to yesterday.
        with usage._connect() as conn:
            conn.execute(
                "UPDATE usage_events SET created_at = ? WHERE id = ?",
                ((datetime.now(UTC) - timedelta(days=1)).isoformat(), entry.id),
            )
        usage.record(bot_id, "m", input_tokens=5)

        assert usage.today(bot_id=bot_id).total_tokens == 5

    def test_by_model_groups_and_orders(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        usage.record(bot_id, "model-a", input_tokens=10, output_tokens=10)
        usage.record(bot_id, "model-b", input_tokens=100, output_tokens=100)
        usage.record(bot_id, "model-a", input_tokens=5, output_tokens=5)

        rows = usage.by_model()

        assert [row["model"] for row in rows] == ["model-b", "model-a"]
        assert rows[1]["tokens"] == 30
        assert rows[1]["runs"] == 2

    def test_zero_and_negative_tokens_are_clamped(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        usage.record(bot_id, "m", input_tokens=-5, output_tokens=0)

        assert usage.summary().input_tokens == 0


class TestBudget:
    def test_token_budget(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        usage.record(bot_id, "m", input_tokens=80, output_tokens=30)
        today = usage.today(bot_id=bot_id)

        assert budget_exceeded(today, token_budget=100, usd_budget=0) is not None
        assert budget_exceeded(today, token_budget=500, usd_budget=0) is None

    def test_usd_budget(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        usage.record(bot_id, "m", cost_usd=1.5)
        today = usage.today(bot_id=bot_id)

        assert budget_exceeded(today, token_budget=0, usd_budget=1.0) is not None
        assert budget_exceeded(today, token_budget=0, usd_budget=2.0) is None

    def test_zero_budgets_mean_unlimited(self, env: tuple[UsageRepository, str]) -> None:
        usage, bot_id = env
        usage.record(bot_id, "m", input_tokens=10_000, cost_usd=99.0)

        assert budget_exceeded(usage.today(), token_budget=0, usd_budget=0) is None
