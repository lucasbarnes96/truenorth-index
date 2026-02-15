from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from models import NowcastSnapshot

DATA_DIR = Path("data")
LATEST_PATH = DATA_DIR / "latest.json"
PUBLISHED_LATEST_PATH = DATA_DIR / "published_latest.json"
HISTORICAL_PATH = DATA_DIR / "historical.json"
RELEASE_DB_PATH = DATA_DIR / "releases.db"

app = FastAPI(title="True Inflation Canada API", version="1.0.0")


def _load_json(path: Path, default: dict | list) -> dict | list:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


@app.get("/v1/nowcast/latest")
def nowcast_latest() -> dict:
    payload = _load_json(PUBLISHED_LATEST_PATH, {})
    if not payload:
        payload = _load_json(LATEST_PATH, {})
    if not payload:
        raise HTTPException(status_code=404, detail="No snapshot available.")
    validated = NowcastSnapshot.model_validate(payload)
    return validated.model_dump(mode="json")


@app.get("/v1/nowcast/history")
def nowcast_history(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> dict:
    history = _load_json(HISTORICAL_PATH, {})
    if not isinstance(history, dict):
        return {"items": []}

    items: list[dict] = []
    for day, payload in sorted(history.items()):
        try:
            day_date = date.fromisoformat(day)
        except ValueError:
            continue
        if start and day_date < start:
            continue
        if end and day_date > end:
            continue
        items.append({"date": day, **payload})
    return {"items": items}


@app.get("/v1/sources/health")
def sources_health() -> dict:
    payload = _load_json(PUBLISHED_LATEST_PATH, {})
    if not payload:
        payload = _load_json(LATEST_PATH, {})
    sources = payload.get("source_health", []) if isinstance(payload, dict) else []
    return {"items": sources}


@app.get("/v1/releases/latest")
def releases_latest() -> dict:
    if not RELEASE_DB_PATH.exists():
        raise HTTPException(status_code=404, detail="No release runs found.")

    with sqlite3.connect(RELEASE_DB_PATH) as conn:
        row = conn.execute(
            "SELECT run_id, created_at, status, blocked_conditions, snapshot_path "
            "FROM release_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No release runs found.")

    run_id, created_at, status, blocked_conditions, snapshot_path = row
    try:
        blocked = json.loads(blocked_conditions)
    except json.JSONDecodeError:
        blocked = []
    return {
        "run_id": run_id,
        "created_at": created_at,
        "status": status,
        "blocked_conditions": blocked,
        "snapshot_path": snapshot_path,
    }


@app.get("/v1/methodology")
def methodology() -> dict:
    return {
        "summary": "Weighted category nowcast using daily and monthly public data sources.",
        "gate_policy": {
            "apify_max_age_days": 14,
            "required_sources": ["apify_loblaws", "statcan_cpi_csv", "statcan_gas_csv"],
            "energy_required_any_of": ["oeb_scrape", "ieso_hoep"],
            "category_min_points": {"food": 5, "housing": 2, "transport": 1, "energy": 1},
            "metadata_required": ["official_cpi.latest_release_month"],
        },
        "limitations": [
            "Experimental nowcast, not an official CPI release.",
            "APIFY is run weekly on free-tier constraints.",
            "Monthly sources may remain fresh for up to 45 days.",
        ],
    }
