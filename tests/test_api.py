from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from api.main import app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None  # type: ignore[assignment]
    app = None  # type: ignore[assignment]


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed")
class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir = Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.published_latest = self.data_dir / "published_latest.json"
        self.historical = self.data_dir / "historical.json"
        self.releases_db = self.data_dir / "releases.db"

        snapshot = {
            "as_of_date": "2026-02-15",
            "timestamp": "2026-02-15T00:00:00+00:00",
            "headline": {
                "nowcast_mom_pct": 0.1,
                "confidence": "medium",
                "coverage_ratio": 0.75,
                "method_label": "test",
            },
            "categories": {
                "food": {"proxy_level": 1.0, "daily_change_pct": 0.1, "weight": 0.165, "points": 8, "status": "fresh"},
                "housing": {"proxy_level": 1.0, "daily_change_pct": 0.1, "weight": 0.3, "points": 3, "status": "fresh"},
                "transport": {"proxy_level": 1.0, "daily_change_pct": 0.1, "weight": 0.15, "points": 2, "status": "fresh"},
                "energy": {"proxy_level": 1.0, "daily_change_pct": 0.1, "weight": 0.08, "points": 2, "status": "fresh"},
            },
            "official_cpi": {"latest_release_month": "2025-12", "mom_pct": 0.2, "yoy_pct": 2.5},
            "bank_of_canada": {},
            "source_health": [
                {
                    "source": "apify_loblaws",
                    "category": "food",
                    "tier": 1,
                    "status": "fresh",
                    "last_success_timestamp": "2026-02-14T00:00:00+00:00",
                    "detail": "ok",
                    "source_run_id": "abc",
                    "age_days": 1,
                    "updated_days_ago": "updated 1 day ago",
                }
            ],
            "notes": [],
            "meta": {},
            "release": {
                "run_id": "run_123",
                "status": "published",
                "blocked_conditions": [],
                "created_at": "2026-02-15T00:00:00+00:00",
                "published_at": "2026-02-15T00:00:00+00:00",
            },
        }
        self.published_latest.write_text(json.dumps(snapshot))
        self.historical.write_text(json.dumps({"2026-02-15": {"headline": {"nowcast_mom_pct": 0.1}}}))

        with sqlite3.connect(self.releases_db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS release_runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, blocked_conditions TEXT NOT NULL, snapshot_path TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO release_runs (run_id, created_at, status, blocked_conditions, snapshot_path) VALUES (?, ?, ?, ?, ?)",
                ("run_123", "2026-02-15T00:00:00+00:00", "published", "[]", "data/runs/run_123.json"),
            )
            conn.commit()

        self.client = TestClient(app)

    def test_latest_endpoint(self) -> None:
        resp = self.client.get("/v1/nowcast/latest")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual("run_123", body["release"]["run_id"])

    def test_methodology_endpoint(self) -> None:
        resp = self.client.get("/v1/methodology")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertIn("gate_policy", body)


if __name__ == "__main__":
    unittest.main()
