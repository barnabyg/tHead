"""Durable accounting contract; provider dispatch is tested by the conversation app."""

import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from budget import Budget, BudgetError  # noqa: E402


class BudgetTests(unittest.TestCase):
    def test_missing_invalid_and_unknown_accounting_never_resets_spend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budget.sqlite"
            with self.assertRaisesRegex(BudgetError, "missing"):
                Budget(path)
            budget = Budget(path, initialize=True)
            reservation = budget.reserve("gpt-6-luna", 1000, 400)
            budget.settle(reservation)
            with self.assertRaisesRegex(BudgetError, "Unknown model"):
                budget.reserve("new-unpriced-model", 1000, 400)
            self.assertEqual(Budget(path, initialize=True).snapshot()["estimated_usd"], 0.000325)
            path.write_bytes(b"broken accounting")
            with self.assertRaises(BudgetError):
                Budget(path, initialize=True)
            with self.assertRaises(BudgetError):
                budget.reserve("gpt-6-luna", 1000, 400)
            path.unlink()
            with self.assertRaisesRegex(BudgetError, "missing"):
                budget.snapshot()

    def test_missing_cancelled_and_invalid_usage_remain_charged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            budget = Budget(Path(temporary) / "budget.sqlite", initialize=True)
            reservation = budget.reserve("gpt-6-luna", 1000, 400)
            usage = budget.settle(reservation)
            self.assertTrue(usage["estimated"])
            self.assertIsNone(usage["input_tokens"])
            self.assertEqual(usage["estimated_usd"], 0.000325)
            self.assertEqual(budget.settle(reservation, 10, 10), usage)
            reservation = budget.reserve("gpt-6-luna", 1000, 400)
            budget.settle(reservation, -1, 10)
            self.assertEqual(budget.snapshot()["estimated_usd"], 0.00065)

    def test_month_rollover_retains_inflight_allowance_and_rejects_clock_rollback(self) -> None:
        instant = datetime(2026, 11, 30, 23, 59, 59, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budget.sqlite"
            budget = Budget(path, initialize=True, clock=lambda: instant)
            pending = budget.reserve("gpt-6-luna", 0, 80_000_000)
            instant = datetime(2026, 12, 1, tzinfo=timezone.utc)
            self.assertEqual(budget.snapshot()["month"], "2026-12")
            with self.assertRaisesRegex(BudgetError, "insufficient"):
                budget.reserve("gpt-6-luna", 1, 1)
            budget.settle(pending, 0, 10)
            self.assertEqual(budget.snapshot()["remaining_usd"], 40)
            budget.reserve("gpt-6-luna", 1, 1)
            instant = datetime(2026, 11, 30, tzinfo=timezone.utc)
            with self.assertRaisesRegex(BudgetError, "backwards"):
                budget.reserve("gpt-6-luna", 1, 1)

    def test_concurrent_app_instances_cannot_reserve_the_same_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budget.sqlite"
            Budget(path, initialize=True)

            def reserve(_: int) -> bool:
                try:
                    Budget(path).reserve("gpt-6-luna", 0, 80_000_000)
                    return True
                except BudgetError:
                    return False

            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(reserve, range(8))), 1)
            self.assertEqual(Budget(path).snapshot()["remaining_usd"], 0)

    def test_limit_rejects_without_a_new_reservation_and_retry_needs_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            budget = Budget(Path(temporary) / "budget.sqlite", initialize=True)
            first = budget.reserve("gpt-6-luna", 0, 79_999_999)
            self.assertEqual(budget.snapshot()["remaining_usd"], 0.0000005)
            with self.assertRaisesRegex(BudgetError, "insufficient"):
                budget.reserve("gpt-6-luna", 1, 1)
            budget.settle(first)
            retry = budget.reserve("gpt-6-luna", 0, 1)
            self.assertEqual(budget.snapshot()["remaining_usd"], 0)
            budget.settle(retry)
            with self.assertRaisesRegex(BudgetError, "insufficient"):
                budget.reserve("gpt-6-luna", 0, 1)

    def test_reservation_survives_restart_and_reconciles_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "budget.sqlite"
            budget = Budget(path, initialize=True)
            reservation = budget.reserve("gpt-6-luna", 1000, 400)
            self.assertEqual(budget.snapshot()["reserved_usd"], 0.000325)
            restarted = Budget(path)
            self.assertEqual(restarted.snapshot()["reserved_usd"], 0.000325)
            usage = restarted.settle(reservation, 100, 20)
            self.assertEqual(usage["estimated_usd"], 0.0000225)
            self.assertEqual(restarted.settle(reservation, 100, 20), usage)
            self.assertEqual(restarted.snapshot()["estimated_usd"], 0.0000225)
            self.assertEqual(restarted.snapshot()["reserved_usd"], 0)


if __name__ == "__main__":
    unittest.main()
