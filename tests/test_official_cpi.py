from __future__ import annotations

import unittest
from unittest.mock import patch

from scrapers.official_cpi import fetch_official_cpi_series, fetch_official_cpi_summary


def _build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    values = [100.0 + i for i in range(14)]
    months = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 3)]
    for idx, value in enumerate(values):
        rows.append(
            {
                "GEO": "Canada",
                "Products and product groups": "All-items",
                "VALUE": str(value),
                "REF_DATE": months[idx],
            }
        )
    return rows


class OfficialCpiTests(unittest.TestCase):
    def test_fetch_official_cpi_series_sorted_with_mom_and_yoy(self) -> None:
        with patch("scrapers.official_cpi._load_cpi_rows", return_value=_build_rows()):
            out = fetch_official_cpi_series()

        self.assertEqual(14, len(out))
        self.assertEqual("2024-01", out[0]["ref_date"])
        self.assertIsNone(out[0]["mom_pct"])
        self.assertIsNone(out[11]["yoy_pct"])
        self.assertAlmostEqual(0.893, out[-1]["mom_pct"], places=3)
        self.assertAlmostEqual(11.881, out[-1]["yoy_pct"], places=3)

    def test_fetch_official_cpi_summary_uses_series_shape(self) -> None:
        with patch("scrapers.official_cpi._load_cpi_rows", return_value=_build_rows()):
            summary = fetch_official_cpi_summary()

        self.assertEqual("2025-02", summary["latest_release_month"])
        self.assertAlmostEqual(0.893, summary["mom_pct"], places=3)
        self.assertAlmostEqual(11.881, summary["yoy_pct"], places=3)


if __name__ == "__main__":
    unittest.main()
