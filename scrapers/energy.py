from __future__ import annotations

from datetime import datetime, timezone

from .common import fetch_url, parse_floats_from_text, utc_now_iso
from .types import Quote, SourceHealth

OEB_RATES_URL = "https://www.oeb.ca/consumer-information-and-protection/electricity-rates"


def scrape_energy() -> tuple[list[Quote], list[SourceHealth]]:
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
                detail=f"Collected {len(quotes)} electricity observations.",
            )
        )
    except Exception as err:  # pragma: no cover - network dependent
        health.append(
            SourceHealth(
                source="oeb_scrape",
                category="energy",
                tier=2,
                status="missing",
                last_success_timestamp=None,
                detail=f"Fetch failed: {err}",
            )
        )

    return quotes, health
