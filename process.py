from __future__ import annotations

import json
import sqlite3
import statistics
import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from models import NowcastSnapshot
from scrapers import (
    Quote,
    SourceHealth,
    fetch_boc_cpi,
    fetch_official_cpi_summary,
    scrape_energy,
    scrape_food,
    scrape_food_statcan,
    scrape_grocery_apify,
    scrape_housing,
    scrape_transport,
)

DATA_DIR = Path("data")
RUNS_DIR = DATA_DIR / "runs"
LATEST_PATH = DATA_DIR / "latest.json"
PUBLISHED_LATEST_PATH = DATA_DIR / "published_latest.json"
HISTORICAL_PATH = DATA_DIR / "historical.json"
RELEASE_DB_PATH = DATA_DIR / "releases.db"

CATEGORY_WEIGHTS = {
    "food": 0.165,
    "housing": 0.300,
    "transport": 0.150,
    "energy": 0.080,
}

VALUE_BOUNDS = {
    "food": (0.1, 500.0),
    "housing": (1.0, 400.0),
    "transport": (50.0, 300.0),
    "energy": (0.1, 100.0),
}

OUTLIER_THRESHOLD_PCT = {
    "food": 60.0,
    "housing": 30.0,
    "transport": 40.0,
    "energy": 50.0,
}

CATEGORY_MIN_POINTS = {
    "food": 5,
    "housing": 2,
    "transport": 1,
    "energy": 1,
}

SOURCE_SLA_DAYS = {
    "apify_loblaws": 14,
    "openfoodfacts_api": 2,
    "oeb_scrape": 2,
    "statcan_energy_cpi_csv": 45,
    "statcan_food_prices": 45,
    "statcan_gas_csv": 45,
    "statcan_cpi_csv": 45,
}

APIFY_MAX_AGE_DAYS = 14
METHOD_LABEL = "Daily nowcast vs prior month basket proxy"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def round_or_none(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, places)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def source_age_days(last_success_timestamp: str | None, now: datetime | None = None) -> int | None:
    stamp = parse_iso_datetime(last_success_timestamp)
    if stamp is None:
        return None
    if now is None:
        now = utc_now()
    return max(0, (now.date() - stamp.date()).days)


def human_age(age_days: int | None) -> str:
    if age_days is None:
        return "unknown"
    if age_days == 0:
        return "updated today"
    if age_days == 1:
        return "updated 1 day ago"
    return f"updated {age_days} days ago"


def load_json(path: Path, default: dict | list) -> dict | list:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def load_historical() -> dict:
    data = load_json(HISTORICAL_PATH, {})
    return data if isinstance(data, dict) else {}


def dedupe_quotes(quotes: list[Quote]) -> list[Quote]:
    deduped: dict[str, Quote] = {}
    for quote in quotes:
        key = f"{quote.source}|{quote.item_id}|{quote.observed_at.isoformat()}"
        deduped[key] = quote
    return list(deduped.values())


def apply_range_checks(quotes: list[Quote]) -> tuple[list[Quote], int]:
    valid: list[Quote] = []
    rejected = 0
    for quote in quotes:
        lower, upper = VALUE_BOUNDS[quote.category]
        if quote.value <= 0 or quote.value < lower or quote.value > upper:
            rejected += 1
            continue
        valid.append(quote)
    return valid, rejected


def previous_category_median(historical: dict, category: str) -> float | None:
    if not historical:
        return None
    latest_day = sorted(historical.keys())[-1]
    value = historical.get(latest_day, {}).get("categories", {}).get(category, {}).get("proxy_level")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_outlier_filter(quotes: list[Quote], historical: dict) -> tuple[list[Quote], int]:
    by_category: dict[str, list[Quote]] = defaultdict(list)
    for quote in quotes:
        by_category[quote.category].append(quote)

    kept: list[Quote] = []
    anomalies = 0
    for category, cat_quotes in by_category.items():
        median_today = statistics.median(q.value for q in cat_quotes)
        median_prev = previous_category_median(historical, category)
        if median_prev is None or median_prev <= 0:
            kept.extend(cat_quotes)
            continue

        delta_pct = abs((median_today / median_prev - 1) * 100)
        threshold = OUTLIER_THRESHOLD_PCT[category]
        if delta_pct > threshold:
            anomalies += len(cat_quotes)
            continue

        kept.extend(cat_quotes)

    return kept, anomalies


def recompute_source_health(raw_health: list[SourceHealth], now: datetime) -> list[dict]:
    computed: list[dict] = []
    for entry in raw_health:
        payload = asdict(entry)
        age_days = source_age_days(entry.last_success_timestamp, now=now)
        sla_days = SOURCE_SLA_DAYS.get(entry.source)
        if age_days is None:
            status = "missing"
        elif sla_days is not None and age_days <= sla_days:
            status = "fresh"
        else:
            status = "stale"

        payload["status"] = status
        payload["age_days"] = age_days
        payload["updated_days_ago"] = human_age(age_days)
        computed.append(payload)
    return computed


def summarize_categories(quotes: list[Quote], source_health: list[dict]) -> dict:
    by_category: dict[str, list[Quote]] = defaultdict(list)
    for quote in quotes:
        by_category[quote.category].append(quote)

    source_by_name = {s["source"]: s for s in source_health}

    summary: dict[str, dict] = {}
    for category, weight in CATEGORY_WEIGHTS.items():
        cat_quotes = by_category.get(category, [])
        level = round_or_none(statistics.mean([q.value for q in cat_quotes]), 4) if cat_quotes else None

        status = "missing"
        if cat_quotes:
            category_statuses = [h["status"] for h in source_health if h["category"] == category]
            status = "fresh" if "fresh" in category_statuses else "stale"

        if category == "food":
            apify = source_by_name.get("apify_loblaws")
            if not apify or apify["status"] != "fresh":
                status = "missing"

        summary[category] = {
            "proxy_level": level,
            "daily_change_pct": None,
            "weight": weight,
            "points": len(cat_quotes),
            "status": status,
        }

    return summary


def compute_daily_changes(categories: dict, historical: dict) -> None:
    if not historical:
        return

    latest_day = sorted(historical.keys())[-1]
    prev_categories = historical.get(latest_day, {}).get("categories", {})

    for category, payload in categories.items():
        current = payload.get("proxy_level")
        prev = prev_categories.get(category, {}).get("proxy_level")
        if current is None or prev in (None, 0):
            payload["daily_change_pct"] = None
            continue
        payload["daily_change_pct"] = round_or_none(((float(current) / float(prev)) - 1) * 100)


def compute_coverage(categories: dict) -> float:
    covered = 0.0
    for payload in categories.values():
        if payload["status"] in {"fresh", "stale"} and payload["proxy_level"] is not None:
            covered += payload["weight"]
    total = sum(CATEGORY_WEIGHTS.values())
    return round(covered / total, 4) if total else 0.0


def compute_nowcast_mom(categories: dict, historical: dict) -> float | None:
    if not historical:
        return None

    latest_day = sorted(historical.keys())[-1]
    prev_categories = historical.get(latest_day, {}).get("categories", {})

    weighted_change = 0.0
    effective_weight = 0.0
    for category, payload in categories.items():
        current = payload.get("proxy_level")
        prev = prev_categories.get(category, {}).get("proxy_level")
        weight = payload["weight"]
        if current is None or prev in (None, 0):
            continue
        category_change = (float(current) / float(prev) - 1) * 100
        weighted_change += category_change * weight
        effective_weight += weight

    if effective_weight == 0:
        return None

    normalized_change = weighted_change / effective_weight
    return round_or_none(normalized_change)


def compute_confidence(coverage_ratio: float, anomalies: int, blocked_conditions: list[str]) -> str:
    if blocked_conditions:
        return "low"

    if coverage_ratio >= 0.9:
        confidence = "high"
    elif coverage_ratio >= 0.6:
        confidence = "medium"
    else:
        confidence = "low"

    if anomalies > 0 and confidence == "high":
        return "medium"
    if anomalies > 0 and confidence == "medium":
        return "low"
    return confidence


def compute_top_driver(categories: dict) -> dict:
    """Return top absolute weighted category contribution for Easy mode cards."""
    best_category: str | None = None
    best_contribution: float | None = None
    for category, payload in categories.items():
        change = payload.get("daily_change_pct")
        weight = payload.get("weight", 0.0)
        if change is None:
            continue
        contribution = float(change) * float(weight)
        if best_contribution is None or abs(contribution) > abs(best_contribution):
            best_category = category
            best_contribution = contribution

    if best_category is None:
        return {"category": None, "contribution_pct": None}
    return {
        "category": best_category,
        "contribution_pct": round_or_none(best_contribution, 4),
    }


def build_notes(categories: dict, anomalies: int, rejected_points: int, blocked_conditions: list[str]) -> list[str]:
    notes: list[str] = [
        "This is an experimental nowcast estimate and not an official CPI release.",
        "Methodology: weighted category proxy changes vs prior period baseline.",
    ]

    missing = [k for k, v in categories.items() if v["status"] == "missing"]
    stale = [k for k, v in categories.items() if v["status"] == "stale"]
    if missing:
        notes.append(f"Missing categories today: {', '.join(missing)}. Confidence is downgraded.")
    if stale:
        notes.append(f"Stale categories used: {', '.join(stale)}.")
    if rejected_points:
        notes.append(f"Dropped {rejected_points} points via range checks.")
    if anomalies:
        notes.append(f"Dropped {anomalies} points via day-over-day anomaly filter.")
    if blocked_conditions:
        notes.append("Release gate failed: " + "; ".join(blocked_conditions))

    return notes


def collect_all_quotes() -> tuple[list[Quote], list[SourceHealth]]:
    quotes: list[Quote] = []
    health: list[SourceHealth] = []

    for scraper in (scrape_food, scrape_food_statcan, scrape_grocery_apify, scrape_transport, scrape_housing, scrape_energy):
        scraper_quotes, scraper_health = scraper()
        quotes.extend(scraper_quotes)
        health.extend(scraper_health)

    return quotes, health


def evaluate_gate(snapshot: dict) -> list[str]:
    blocked: list[str] = []
    source_by_name = {s["source"]: s for s in snapshot["source_health"]}

    apify = source_by_name.get("apify_loblaws")
    apify_age = apify.get("age_days") if apify else None
    if not apify or apify.get("status") == "missing" or apify_age is None or apify_age > APIFY_MAX_AGE_DAYS:
        blocked.append("Gate A failed: APIFY missing or older than 14 days.")

    for required in ("statcan_cpi_csv", "statcan_gas_csv"):
        if source_by_name.get(required, {}).get("status") == "missing":
            blocked.append(f"Gate B failed: required source {required} is missing.")

    energy_ok = False
    for source in ("oeb_scrape", "statcan_energy_cpi_csv"):
        state = source_by_name.get(source, {}).get("status")
        if state in {"fresh", "stale"}:
            energy_ok = True
            break
    if not energy_ok:
        blocked.append("Gate B failed: no usable energy source.")

    for category, payload in snapshot["categories"].items():
        min_points = CATEGORY_MIN_POINTS[category]
        if payload["points"] < min_points:
            blocked.append(f"Gate D failed: category {category} has fewer than {min_points} points.")

    official_month = snapshot.get("official_cpi", {}).get("latest_release_month")
    if not official_month:
        blocked.append("Gate E failed: official CPI metadata missing latest release month.")

    return blocked


def validate_snapshot(snapshot: dict) -> list[str]:
    try:
        NowcastSnapshot.model_validate(snapshot)
        return []
    except Exception as err:
        return [f"Gate C failed: snapshot schema validation error: {err}"]


def ensure_release_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(RELEASE_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS release_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                blocked_conditions TEXT NOT NULL,
                snapshot_path TEXT NOT NULL
            )
            """
        )
        conn.commit()


def record_release_run(run_id: str, created_at: str, status: str, blocked_conditions: list[str], snapshot_path: str) -> None:
    ensure_release_db()
    with sqlite3.connect(RELEASE_DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO release_runs (run_id, created_at, status, blocked_conditions, snapshot_path) VALUES (?, ?, ?, ?, ?)",
            (run_id, created_at, status, json.dumps(blocked_conditions), snapshot_path),
        )
        conn.commit()


def update_historical(snapshot: dict, historical: dict) -> dict:
    day = snapshot["as_of_date"]
    official = snapshot.get("official_cpi", {})
    nowcast_mom = snapshot.get("headline", {}).get("nowcast_mom_pct")
    official_mom = official.get("mom_pct")
    divergence = None
    if nowcast_mom is not None and official_mom is not None:
        divergence = round_or_none(float(nowcast_mom) - float(official_mom), 4)

    historical[day] = {
        "headline": {
            "nowcast_mom_pct": nowcast_mom,
            "confidence": snapshot["headline"]["confidence"],
            "coverage_ratio": snapshot["headline"]["coverage_ratio"],
            "divergence_mom_pct": divergence,
        },
        "official_cpi": {
            "latest_release_month": official.get("latest_release_month"),
            "mom_pct": official_mom,
            "yoy_pct": official.get("yoy_pct"),
        },
        "categories": {
            k: {
                "proxy_level": v["proxy_level"],
                "daily_change_pct": v["daily_change_pct"],
                "status": v["status"],
            }
            for k, v in snapshot["categories"].items()
        },
        "source_health": [
            {
                "source": s["source"],
                "status": s["status"],
                "category": s["category"],
                "tier": s["tier"],
                "age_days": s.get("age_days"),
            }
            for s in snapshot["source_health"]
        ],
        "release": snapshot["release"],
    }
    return historical


def build_snapshot() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    historical = load_historical()

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = utc_now().replace(microsecond=0)

    raw_quotes, raw_source_health = collect_all_quotes()
    source_health = recompute_source_health(raw_source_health, now=now)

    deduped = dedupe_quotes(raw_quotes)
    range_valid, rejected_points = apply_range_checks(deduped)
    filtered, anomalies = apply_outlier_filter(range_valid, historical)

    categories = summarize_categories(filtered, source_health)
    compute_daily_changes(categories, historical)

    coverage_ratio = compute_coverage(categories)
    nowcast_mom = compute_nowcast_mom(categories, historical)

    snapshot = {
        "as_of_date": now.date().isoformat(),
        "timestamp": now.isoformat(),
        "headline": {
            "nowcast_mom_pct": nowcast_mom,
            "confidence": "low",
            "coverage_ratio": coverage_ratio,
            "method_label": METHOD_LABEL,
        },
        "categories": categories,
        "official_cpi": fetch_official_cpi_summary(),
        "bank_of_canada": fetch_boc_cpi(),
        "source_health": source_health,
        "notes": [],
        "meta": {
            "total_raw_points": len(raw_quotes),
            "total_points_after_dedupe": len(deduped),
            "total_points_after_quality_filters": len(filtered),
            "anomaly_points": anomalies,
            "rejected_points": rejected_points,
            "top_driver": compute_top_driver(categories),
        },
        "release": {
            "run_id": run_id,
            "status": "started",
            "lifecycle_states": ["started"],
            "blocked_conditions": [],
            "created_at": now.isoformat(),
            "published_at": None,
        },
    }

    snapshot["release"]["status"] = "completed"
    snapshot["release"]["lifecycle_states"].append("completed")
    blocked_conditions = evaluate_gate(snapshot)
    blocked_conditions.extend(validate_snapshot(snapshot))

    status = "published" if not blocked_conditions else "failed_gate"
    snapshot["release"]["status"] = status
    snapshot["release"]["lifecycle_states"].append(status)
    snapshot["release"]["blocked_conditions"] = blocked_conditions
    if status == "published":
        snapshot["release"]["published_at"] = now.isoformat()

    snapshot["headline"]["confidence"] = compute_confidence(coverage_ratio, anomalies, blocked_conditions)
    snapshot["notes"] = build_notes(categories, anomalies, rejected_points, blocked_conditions)
    return snapshot


def write_outputs(snapshot: dict) -> None:
    historical = load_historical()
    run_id = snapshot["release"]["run_id"]
    run_path = RUNS_DIR / f"{run_id}.json"

    LATEST_PATH.write_text(json.dumps(snapshot, indent=2))
    run_path.write_text(json.dumps(snapshot, indent=2))

    status = snapshot["release"]["status"]
    if status == "published":
        PUBLISHED_LATEST_PATH.write_text(json.dumps(snapshot, indent=2))
        historical = update_historical(snapshot, historical)
        HISTORICAL_PATH.write_text(json.dumps(historical, indent=2))

    record_release_run(
        run_id=run_id,
        created_at=snapshot["release"]["created_at"],
        status=status,
        blocked_conditions=snapshot["release"]["blocked_conditions"],
        snapshot_path=str(run_path),
    )


def main() -> int:
    snap = build_snapshot()
    write_outputs(snap)
    status = snap["release"]["status"]
    blocked = snap["release"].get("blocked_conditions", [])
    print(f"Run status: {status}")
    print(
        "Summary: "
        f"confidence={snap['headline']['confidence']} coverage={snap['headline']['coverage_ratio']} "
        f"sources_ok={sum(1 for s in snap['source_health'] if s['status'] in {'fresh', 'stale'})}/"
        f"{len(snap['source_health'])}"
    )
    if blocked:
        print("Blocked conditions:")
        for reason in blocked:
            print(f"- {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
