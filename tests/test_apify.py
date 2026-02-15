from __future__ import annotations

import unittest
from datetime import date

from scrapers.grocery_apify import normalize_apify_item


class ApifyNormalizationTests(unittest.TestCase):
    def test_normalize_apify_item_happy_path(self) -> None:
        item = {
            "name": "Milk 2L",
            "price": {"value": 5.49},
            "packageSize": "2 L",
        }
        quote = normalize_apify_item(item=item, observed=date(2026, 2, 15), source_run_id="run123")
        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual("food", quote.category)
        self.assertEqual("apify_loblaws", quote.source)
        self.assertEqual("run123", quote.source_run_id)
        self.assertGreater(quote.value, 0)
        self.assertIn("-", quote.item_id)

    def test_normalize_apify_item_rejects_missing_price(self) -> None:
        item = {"name": "Milk 2L", "price": None}
        quote = normalize_apify_item(item=item, observed=date(2026, 2, 15), source_run_id="run123")
        self.assertIsNone(quote)


if __name__ == "__main__":
    unittest.main()
