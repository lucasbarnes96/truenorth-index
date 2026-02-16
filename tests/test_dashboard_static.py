from __future__ import annotations

import unittest
from pathlib import Path


class DashboardStaticTests(unittest.TestCase):
    def test_drivers_placeholder_copy_present(self) -> None:
        html = Path("index.html").read_text()
        self.assertIn('id="category-placeholder"', html)
        self.assertIn("Insufficient day-over-day history for category contribution ranking.", html)


if __name__ == "__main__":
    unittest.main()
