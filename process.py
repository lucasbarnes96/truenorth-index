from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from scrapers import (
    Quote,
    SourceHealth,
    fetch_official_cpi_summary,
    scrape_energy,
    scrape_food,
    scrape_housing,
    scrape_transport,
)

DATA_DIR = Path("data")
LATEST_PATH = DATA_DIR / "latest.json"
HISTORICAL_PATH = DATA_DIR / "historical.json"

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

# If a category median moves by more than threshold day-over-day,
# mark records as anomalous and drop them from today.
OUTLIER_THRESHOLD_PCT = {
    "food": 60.0,
    "housing": 30.0,
    "transport": 40.0,
    "energy": 50.0,
}

METHOD_LABEL = "Daily nowcast vs prior month basket proxy"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def round_or_none(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, places)


def load_historical() -> dict:
    if not HISTORICAL_PATH.exists():
        return {}
    return json.loads(HISTORICAL_PATH.read_text())


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


def summarize_categories(quotes: list[Quote], source_health: list[SourceHealth]) -> dict:
    by_category: dict[str, list[Quote]] = defaultdict(list)
    for quote in quotes:
        by_category[quote.category].append(quote)

    summary: dict[str, dict] = {}
    for category, weight in CATEGORY_WEIGHTS.items():
        cat_quotes = by_category.get(category, [])
        level = round_or_none(statistics.mean([q.value for q in cat_quotes]), 4) if cat_quotes else None

        status = "missing"
        if cat_quotes:
            category_statuses = [h.status for h in source_health if h.category == category]
            if "fresh" in category_statuses:
                status = "fresh"
            elif "stale" in category_statuses:
                status = "stale"
            else:
                status = "fresh"

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


def compute_confidence(coverage_ratio: float, anomalies: int) -> str:
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


def build_notes(categories: dict, anomalies: int, rejected_points: int) -> list[str]:
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

    return notes


def serialize_source_health(source_health: list[SourceHealth]) -> list[dict]:
    return [asdict(entry) for entry in source_health]


def collect_all_quotes() -> tuple[list[Quote], list[SourceHealth]]:
    quotes: list[Quote] = []
    health: list[SourceHealth] = []

    for scraper in (scrape_food, scrape_transport, scrape_housing, scrape_energy):
        scraper_quotes, scraper_health = scraper()
        quotes.extend(scraper_quotes)
        health.extend(scraper_health)

    return quotes, health


def build_snapshot() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    historical = load_historical()

    raw_quotes, source_health = collect_all_quotes()
    deduped = dedupe_quotes(raw_quotes)
    range_valid, rejected_points = apply_range_checks(deduped)
    filtered, anomalies = apply_outlier_filter(range_valid, historical)

    categories = summarize_categories(filtered, source_health)
    compute_daily_changes(categories, historical)

    coverage_ratio = compute_coverage(categories)
    nowcast_mom = compute_nowcast_mom(categories, historical)
    confidence = compute_confidence(coverage_ratio, anomalies)

    snapshot = {
        "as_of_date": utc_now().date().isoformat(),
        "timestamp": utc_now().replace(microsecond=0).isoformat(),
        "headline": {
            "nowcast_mom_pct": nowcast_mom,
            "confidence": confidence,
            "coverage_ratio": coverage_ratio,
            "method_label": METHOD_LABEL,
        },
        "categories": categories,
        "official_cpi": fetch_official_cpi_summary(),
        "source_health": serialize_source_health(source_health),
        "notes": build_notes(categories, anomalies, rejected_points),
        "meta": {
            "total_raw_points": len(raw_quotes),
            "total_points_after_dedupe": len(deduped),
            "total_points_after_quality_filters": len(filtered),
            "anomaly_points": anomalies,
            "rejected_points": rejected_points,
        },
    }

    return snapshot


def update_historical(snapshot: dict, historical: dict) -> dict:
    day = snapshot["as_of_date"]
    historical[day] = {
        "headline": {
            "nowcast_mom_pct": snapshot["headline"]["nowcast_mom_pct"],
            "confidence": snapshot["headline"]["confidence"],
            "coverage_ratio": snapshot["headline"]["coverage_ratio"],
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
            }
            for s in snapshot["source_health"]
        ],
    }
    return historical


def write_outputs(snapshot: dict) -> None:
    historical = load_historical()
    historical = update_historical(snapshot, historical)

    LATEST_PATH.write_text(json.dumps(snapshot, indent=2))
    HISTORICAL_PATH.write_text(json.dumps(historical, indent=2))


if __name__ == "__main__":
    snap = build_snapshot()
    write_outputs(snap)
    print(f"Wrote {LATEST_PATH} and {HISTORICAL_PATH}")
    print(
        "Summary: "
        f"confidence={snap['headline']['confidence']} coverage={snap['headline']['coverage_ratio']} "
        f"sources_ok={sum(1 for s in snap['source_health'] if s['status'] in {'fresh', 'stale'})}/"
        f"{len(snap['source_health'])}"
    )
