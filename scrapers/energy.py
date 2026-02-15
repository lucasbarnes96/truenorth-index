"""Energy category scraper — OEB rates + IESO Ontario electricity prices.

Combines:
1. OEB (Ontario Energy Board) rate scraping (existing, fragile)
2. IESO hourly Ontario energy price from public reports (reliable)
"""
from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timezone

from .common import fetch_url, parse_floats_from_text, utc_now_iso, USER_AGENT
from .types import Quote, SourceHealth

OEB_RATES_URL = (
    "https://www.oeb.ca/consumer-information-and-protection/electricity-rates"
)

# IESO publishes Hourly Ontario Energy Price (HOEP) as public XML/CSV reports
# The PUB_PriceHOEP report is updated regularly
IESO_PRICE_REPORT_URL = "http://reports.ieso.ca/public/Price/PUB_Price.csv"


def _scrape_oeb() -> tuple[list[Quote], list[SourceHealth]]:
    """Scrape OEB electricity rates (Ontario-specific, fragile)."""
    quotes: list[Quote] = []
    health: list[SourceHealth] = []
    try:
        html = fetch_url(OEB_RATES_URL)
        values = [v for v in parse_floats_from_text(html) if 1 <= v <= 50]
        values = values[:12]
        observed = datetime.now(timezone.utc).date()
        for i, value in enumerate(values):
            quotes.append(
                Quote(
                    category="energy",
                    item_id=f"oeb_rate_{i}",
                    value=value,
                    observed_at=observed,
                    source="oeb_scrape",
                )
            )
        health.append(
            SourceHealth(
                source="oeb_scrape",
                category="energy",
                tier=2,
                status="fresh" if quotes else "missing",
                last_success_timestamp=utc_now_iso() if quotes else None,
                detail=f"Collected {len(quotes)} OEB rate observations.",
            )
        )
    except Exception as err:
        health.append(
            SourceHealth(
                source="oeb_scrape",
                category="energy",
                tier=2,
                status="missing",
                last_success_timestamp=None,
                detail=f"OEB fetch failed: {err}",
            )
        )
    return quotes, health


def _scrape_ieso() -> tuple[list[Quote], list[SourceHealth]]:
    """Fetch Hourly Ontario Energy Price from IESO public reports."""
    quotes: list[Quote] = []
    health: list[SourceHealth] = []
    try:
        req = urllib.request.Request(
            IESO_PRICE_REPORT_URL,
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="ignore")

        # Parse the CSV — IESO format has header rows then data
        lines = raw.strip().split("\n")
        # Find the header row (contains "Date" and "Hour")
        header_idx = None
        for i, line in enumerate(lines):
            if "Date" in line and "Hour" in line:
                header_idx = i
                break

        if header_idx is not None:
            reader = csv.DictReader(lines[header_idx:])
            latest_row = None
            for row in reader:
                latest_row = row  # Will end up with the last row

            if latest_row:
                # Try to get the HOEP value
                hoep = None
                for key in latest_row:
                    if "HOEP" in key.upper() or "Price" in key:
                        try:
                            hoep = float(latest_row[key])
                            break
                        except (ValueError, TypeError):
                            continue

                if hoep is not None:
                    observed = datetime.now(timezone.utc).date()
                    quotes.append(
                        Quote(
                            category="energy",
                            item_id="ieso_hoep",
                            value=hoep,
                            observed_at=observed,
                            source="ieso_hoep",
                        )
                    )

        health.append(
            SourceHealth(
                source="ieso_hoep",
                category="energy",
                tier=1,
                status="fresh" if quotes else "missing",
                last_success_timestamp=utc_now_iso() if quotes else None,
                detail=f"IESO HOEP: {'collected' if quotes else 'no data found'}.",
            )
        )
    except Exception as err:
        health.append(
            SourceHealth(
                source="ieso_hoep",
                category="energy",
                tier=1,
                status="missing",
                last_success_timestamp=None,
                detail=f"IESO fetch failed: {err}",
            )
        )
    return quotes, health


def scrape_energy() -> tuple[list[Quote], list[SourceHealth]]:
    """Scrape energy data from multiple sources."""
    all_quotes: list[Quote] = []
    all_health: list[SourceHealth] = []

    # Try both sources, accumulate results
    for scraper in (_scrape_oeb, _scrape_ieso):
        q, h = scraper()
        all_quotes.extend(q)
        all_health.extend(h)

    return all_quotes, all_health
