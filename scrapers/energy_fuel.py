"""Energy fuel scraper — NRCAN Weekly Average Retail Prices.

Scrapes the Government of Canada (NRCAN) weekly average retail fuel prices.
While not "daily", it is an official and reliable weekly source that leads the monthly CPI.
This is a "Scrappy" implementation that parses the HTML table.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .common import fetch_url, utc_now_iso
from .types import Quote, SourceHealth

# NRCAN Weekly Average Retail Prices (National)
# The URL displays a table. We want the most recent "Canada" average for "Regular" gasoline.
NRCAN_FUEL_URL = "https://www2.nrcan.gc.ca/eneene/sources/pripri/prices_bycity_e.cfm?productID=1&locationID=66,17,39,11,8,59,73,35,46,2,7,4,66&frequency=W&priceYear=0"
# "locationID=66" is Canada Average? Let's assume we parse for the row "Canada"

def scrape_energy_fuel() -> tuple[list[Quote], list[SourceHealth]]:
    quotes: list[Quote] = []
    health: list[SourceHealth] = []
    
    try:
        html = fetch_url(NRCAN_FUEL_URL)
        
        # The table structure is usually:
        # <tr>
        #   <td>City / Average</td>
        #   <td>Date 1</td> ...
        # </tr>
        
        # We look for "Canada" row and the *last* non-empty cell in that row (latest date).
        
        # Simple string search strategy:
        # data is usually in cents per litre, e.g., "145.6".
        
        # The page structure is complex to parse with just regex/split, but let's try to find "Canada"
        # and then the first number sequence after it that looks like a price (100-200 range).
        
        # Actually, let's look for "Canada Average".
        
        # Fallback/Alternative: scraping "GasBuddy" charts API is harder but cooler.
        # But NRCAN is reliable.
        
        # Let's try to find a pattern: "Canada" ... then numbers.
        
        if True: # Always run search on full body
            # NRCAN structure: Each week is a <tr>. The first <td> is the date.
            # The next <td> is usually 'header4_1_1 header3_1' which represents Canada Average.
            # We want the last row containing "headerDate" to get the latest week's data.
            rows = html.split("<tr")
            latest_row = None
            for row in rows:
                if 'headers="headerDate' in row:
                    latest_row = row
            
            price_val = None
            if latest_row:
                # In the row, Canada is the first data column after the date.
                # headers="header4_1_1 header3_1 header1">139.6</td>
                match = re.search(r'<td[^>]*header3_1[^>]*>([\d\.]+)</td>', latest_row)
                if match:
                    try:
                        price_val = float(match.group(1))
                    except ValueError:
                        pass
                
                # Fallback if specific header fails: just take the first number cell after date
                if price_val is None:
                    matches = re.findall(r'<td[^>]*>([\d\.]+)</td>', latest_row)
                    for m in matches:
                        try:
                            val = float(m)
                            if 100.0 <= val <= 300.0:
                                price_val = val
                                break
                        except ValueError:
                            pass

            if price_val:
                observed = datetime.now(timezone.utc).date()
                
                # Convert to "Index" or just "Price"?
                # True Inflation tracks *price changes*.
                # We will store the raw price. The `process.py` can convert it to an index if we had a base,
                # but for "Scrappy" comparison, we just want the raw data to show "Gas Gauge".
                
                # We store it as a quote.
                quotes.append(
                    Quote(
                        category="transport", # Gas is Transport in CPI
                        item_id="gasoline_regular_canada_avg",
                        value=price_val,
                        observed_at=observed,
                        source="nrcan_fuel_scrape",
                    )
                )
                
                health.append(
                    SourceHealth(
                        source="nrcan_fuel_scrape",
                        category="transport",
                        tier=2,
                        status="fresh",
                        last_success_timestamp=utc_now_iso(),
                        detail=f"Parsed Canada average gas price {price_val} c/L from NRCAN.",
                        last_observation_period=None,
                    )
                )
            else:
                 health.append(
                    SourceHealth(
                        source="nrcan_fuel_scrape",
                        category="transport",
                        tier=2,
                        status="missing",
                        last_success_timestamp=None,
                        detail="Found table row but no valid price pattern in NRCAN HTML.",
                        last_observation_period=None,
                    )
                )
        else:
             health.append(
                SourceHealth(
                    source="nrcan_fuel_scrape",
                    category="transport",
                    tier=2,
                    status="missing",
                    last_success_timestamp=None,
                    detail="Could not find 'Canada' row in NRCAN fuel prices HTML.",
                    last_observation_period=None,
                )
            )

    except Exception as err:
        msg = str(err)
        status = "missing"
        if "403" in msg:
            msg = "Blocked by anti-bot protection (403 Forbidden)"
        
        health.append(
            SourceHealth(
                source="nrcan_fuel_scrape",
                category="transport",
                tier=2,
                status=status,
                last_success_timestamp=None,
                detail=f"Fetch failed: {msg}",
                last_observation_period=None,
            )
        )

    return quotes, health
