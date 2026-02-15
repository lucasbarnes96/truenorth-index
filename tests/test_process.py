from __future__ import annotations

import unittest
from datetime import date

from process import (
    CATEGORY_WEIGHTS,
    compute_confidence,
    compute_coverage,
    dedupe_quotes,
    evaluate_gate,
)
from scrapers.types import Quote


class ProcessTests(unittest.TestCase):
    def test_dedupe_quotes(self) -> None:
        q1 = Quote("food", "milk", 4.0, date(2026, 2, 15), "src")
        q2 = Quote("food", "milk", 5.0, date(2026, 2, 15), "src")
        deduped = dedupe_quotes([q1, q2])
        self.assertEqual(1, len(deduped))
        self.assertEqual(5.0, deduped[0].value)

    def test_compute_coverage(self) -> None:
        categories = {
            "food": {"status": "fresh", "proxy_level": 1.0, "weight": CATEGORY_WEIGHTS["food"]},
            "housing": {"status": "missing", "proxy_level": None, "weight": CATEGORY_WEIGHTS["housing"]},
            "transport": {"status": "fresh", "proxy_level": 1.0, "weight": CATEGORY_WEIGHTS["transport"]},
            "energy": {"status": "stale", "proxy_level": 1.0, "weight": CATEGORY_WEIGHTS["energy"]},
        }
        coverage = compute_coverage(categories)
        self.assertGreater(coverage, 0)
        self.assertLess(coverage, 1)

    def test_compute_confidence(self) -> None:
        self.assertEqual("high", compute_confidence(0.95, 0, []))
        self.assertEqual("medium", compute_confidence(0.7, 0, []))
        self.assertEqual("low", compute_confidence(0.4, 0, []))
        self.assertEqual("medium", compute_confidence(0.95, 3, []))
        self.assertEqual("low", compute_confidence(0.7, 3, []))
        self.assertEqual("low", compute_confidence(0.95, 0, ["gate failed"]))

    def test_evaluate_gate_pass(self) -> None:
        snapshot = {
            "source_health": [
                {"source": "apify_loblaws", "status": "fresh", "age_days": 1},
                {"source": "statcan_cpi_csv", "status": "fresh", "age_days": 2},
                {"source": "statcan_gas_csv", "status": "fresh", "age_days": 2},
                {"source": "oeb_scrape", "status": "fresh", "age_days": 0},
            ],
            "categories": {
                "food": {"points": 10},
                "housing": {"points": 3},
                "transport": {"points": 1},
                "energy": {"points": 1},
            },
            "official_cpi": {"latest_release_month": "2025-12"},
        }
        self.assertEqual([], evaluate_gate(snapshot))

    def test_evaluate_gate_fail_when_apify_stale(self) -> None:
        snapshot = {
            "source_health": [
                {"source": "apify_loblaws", "status": "stale", "age_days": 20},
                {"source": "statcan_cpi_csv", "status": "fresh", "age_days": 2},
                {"source": "statcan_gas_csv", "status": "fresh", "age_days": 2},
                {"source": "oeb_scrape", "status": "fresh", "age_days": 0},
            ],
            "categories": {
                "food": {"points": 10},
                "housing": {"points": 3},
                "transport": {"points": 1},
                "energy": {"points": 1},
            },
            "official_cpi": {"latest_release_month": "2025-12"},
        }
        blocked = evaluate_gate(snapshot)
        self.assertTrue(any("Gate A failed" in item for item in blocked))


if __name__ == "__main__":
    unittest.main()
