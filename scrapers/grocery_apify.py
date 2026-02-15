"""Grocery scraper using Apify (Loblaws Grocery Scraper).

Uses the Apify Client to run the 'Loblaws Grocery Scraper' actor.
Ref: https://apify.com/ko_red/loblaws-grocery-scraper

This is Phase 3 of the implementation plan.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from apify_client import ApifyClient
except ImportError:
    ApifyClient = None

from .common import utc_now_iso
from .types import Quote, SourceHealth

# Actor ID for "Loblaws Grocery Scraper"
ACTOR_ID = "sunny_eternity/loblaws-grocery-scraper"

# Loblaws banners to target
BANNERS = ["superstore", "nofrills"]


def scrape_grocery_apify() -> tuple[list[Quote], list[SourceHealth]]:
    """Run the Apify Loblaws scraper to get fresh grocery prices."""
    token = os.getenv("APIFY_TOKEN")
    
    # Manually load from .env if not found in environment
    if not token and os.path.exists(".env"):
        try:
            with open(".env", "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("APIFY_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass

    if not token:
        return [], [
            SourceHealth(
                source="apify_loblaws",
                category="food",
                tier=1,
                status="missing",
                last_success_timestamp=None,
                detail="APIFY_TOKEN not found in environment.",
            )
        ]

    if ApifyClient is None:
        return [], [
            SourceHealth(
                source="apify_loblaws",
                category="food",
                tier=1,
                status="missing",
                last_success_timestamp=None,
                detail="apify-client library not installed.",
            )
        ]

    quotes: list[Quote] = []
    health: list[SourceHealth] = []

    try:
        client = ApifyClient(token)

        # Use a category URL instead of search queries
        category_url = "https://www.realcanadiansuperstore.ca/food/dairy-eggs/c/28003"
        
        # Configure the run
        run_input = {
            "categoryUrl": category_url,
            "maxItems": 50,  # Limit to save CU
            "proxyConfig": {"useApifyProxy": True},
        }

        # Run the actor
        run = client.actor(ACTOR_ID).call(run_input=run_input)

        # Fetch results
        dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
        
        observed = datetime.now(timezone.utc).date()
        
        for item in dataset_items:
            price = item.get("price", {}).get("value")
            name = item.get("name")
            if price and name:
                # Clean up the name for item_id
                item_id = name.lower().split(",")[0].replace(" ", "_").strip()
                # Basic validation
                if len(item_id) > 50:
                    item_id = item_id[:50]
                
                quotes.append(
                    Quote(
                        category="food",
                        item_id=item_id,
                        value=float(price),
                        observed_at=observed,
                        source="apify_loblaws",
                    )
                )

        health.append(
            SourceHealth(
                source="apify_loblaws",
                category="food",
                tier=1,
                status="fresh" if quotes else "missing",
                last_success_timestamp=utc_now_iso() if quotes else None,
                detail=f"Collected {len(quotes)} prices from Apify Loblaws scraper.",
            )
        )

    except Exception as err:
        health.append(
            SourceHealth(
                source="apify_loblaws",
                category="food",
                tier=1,
                status="missing",
                last_success_timestamp=None,
                detail=f"Apify run failed: {err}",
            )
        )

    return quotes, health
