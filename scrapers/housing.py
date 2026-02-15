from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone

from .common import fetch_url, utc_now_iso
from .types import Quote, SourceHealth

# Statistics Canada table 18-10-0004-01 (Consumer Price Index, monthly)
STATCAN_CPI_ZIP = "https://www150.statcan.gc.ca/n1/en/tbl/csv/18100004-eng.zip"


TARGET_VECTOR_HOUSING = {"Rent", "Shelter"}


def scrape_housing() -> tuple[list[Quote], list[SourceHealth]]:
    quotes: list[Quote] = []
    health: list[SourceHealth] = []

    try:
        raw = fetch_url(STATCAN_CPI_ZIP)
        data = raw.encode("utf-8", errors="ignore")

        # Some endpoints return binary bytes that may be mangled by decode/encode;
        # recover by fetching bytes directly if needed.
        if not zipfile.is_zipfile(io.BytesIO(data)):
            import urllib.request

            req = urllib.request.Request(STATCAN_CPI_ZIP, headers={"User-Agent": "TrueNorthIndexBot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csv_name = next(name for name in zf.namelist() if name.endswith(".csv"))
            with zf.open(csv_name) as handle:
                decoded = io.TextIOWrapper(handle, encoding="utf-8", errors="ignore")
                rows = list(csv.DictReader(decoded))

        latest_by_product: dict[str, tuple[str, float]] = {}
        for row in rows:
            if row.get("GEO") != "Canada":
                continue
            product = (row.get("Products and product groups") or "").strip()
            if product not in TARGET_VECTOR_HOUSING:
                continue
            value_raw = row.get("VALUE")
            ref_date = row.get("REF_DATE")
            if not value_raw or not ref_date:
                continue
            try:
                value = float(value_raw)
            except ValueError:
                continue
            prev = latest_by_product.get(product)
            if prev is None or ref_date > prev[0]:
                latest_by_product[product] = (ref_date, value)

        observed = datetime.now(timezone.utc).date()
        for product, (_, value) in latest_by_product.items():
            quotes.append(
                Quote(
                    category="housing",
                    item_id=product.lower().replace(" ", "_"),
                    value=value,
                    observed_at=observed,
                    source="statcan_cpi_table",
                )
            )

        health.append(
            SourceHealth(
                source="statcan_cpi_table",
                category="housing",
                tier=1,
                status="stale" if quotes else "missing",
                last_success_timestamp=utc_now_iso() if quotes else None,
                detail=f"Collected {len(quotes)} monthly CPI housing proxies.",
            )
        )
    except Exception as err:  # pragma: no cover - network dependent
        health.append(
            SourceHealth(
                source="statcan_cpi_table",
                category="housing",
                tier=1,
                status="missing",
                last_success_timestamp=None,
                detail=f"Fetch failed: {err}",
            )
        )

    return quotes, health
