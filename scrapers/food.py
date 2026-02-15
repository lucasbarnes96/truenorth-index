from __future__ import annotations

from datetime import datetime, timezone

from .common import fetch_json, utc_now_iso
from .types import Quote, SourceHealth

OPEN_FOOD_FACTS_URL = "https://prices.openfoodfacts.org/api/v1/prices?size=250&location_country=CA"


def scrape_food() -> tuple[list[Quote], list[SourceHealth]]:
    quotes: list[Quote] = []
    health: list[SourceHealth] = []
    now = utc_now_iso()

    try:
        data = fetch_json(OPEN_FOOD_FACTS_URL)
        items = data.get("items", []) if isinstance(data, dict) else []
        for item in items:
            price = item.get("price")
            product = item.get("product_name") or "unknown_product"
            date_raw = item.get("date")
            if price is None:
                continue
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue

            observed_at = datetime.now(timezone.utc).date()
            if isinstance(date_raw, str) and date_raw[:10]:
                try:
                    observed_at = datetime.fromisoformat(date_raw[:10]).date()
                except ValueError:
                    pass

            quotes.append(
                Quote(
                    category="food",
                    item_id=product.strip().lower()[:120],
                    value=value,
                    observed_at=observed_at,
                    source="openfoodfacts_api",
                )
            )

        status = "fresh" if quotes else "missing"
        health.append(
            SourceHealth(
                source="openfoodfacts_api",
                category="food",
                tier=1,
                status=status,
                last_success_timestamp=now if quotes else None,
                detail=f"Collected {len(quotes)} records from OpenFoodFacts API.",
            )
        )
    except Exception as err:  # pragma: no cover - network dependent
        health.append(
            SourceHealth(
                source="openfoodfacts_api",
                category="food",
                tier=1,
                status="missing",
                last_success_timestamp=None,
                detail=f"Fetch failed: {err}",
            )
        )

    return quotes, health
