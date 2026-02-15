"""Bank of Canada Valet API — official CPI baseline data.

The Valet API is free, requires no API key, and returns JSON.
Documentation: https://www.bankofcanada.ca/valet/docs
"""
from __future__ import annotations

from datetime import datetime, timezone

from .common import fetch_json, utc_now_iso
from .types import Quote, SourceHealth

# Series IDs from the CPI_MONTHLY group
BOC_SERIES = {
    "total_cpi": "V41690973",
    "cpi_trim": "CPI_TRIM",
    "cpi_median": "CPI_MEDIAN",
    "cpi_common": "CPI_COMMON",
}

BOC_BASE_URL = "https://www.bankofcanada.ca/valet/observations"


def fetch_boc_cpi() -> dict:
    """Fetch the latest CPI observations from Bank of Canada Valet API.

    Returns a dict with official CPI data suitable for the snapshot.
    This does NOT produce Quote objects because it's a baseline comparison,
    not a category proxy.
    """
    result: dict = {
        "total_cpi": None,
        "total_cpi_date": None,
        "cpi_trim": None,
        "cpi_median": None,
        "cpi_common": None,
    }

    try:
        # Fetch Total CPI (last 2 months for MoM calculation)
        url = f"{BOC_BASE_URL}/{BOC_SERIES['total_cpi']}/json?recent=13"
        data = fetch_json(url)
        observations = data.get("observations", [])

        if observations:
            latest = observations[-1]
            latest_val = latest.get(BOC_SERIES["total_cpi"], {}).get("v")
            latest_date = latest.get("d")

            if latest_val is not None:
                result["total_cpi"] = float(latest_val)
                result["total_cpi_date"] = latest_date

            # Calculate MoM and YoY if we have enough data
            if len(observations) >= 2:
                prev = observations[-2]
                prev_val = prev.get(BOC_SERIES["total_cpi"], {}).get("v")
                if prev_val and latest_val:
                    mom = ((float(latest_val) / float(prev_val)) - 1) * 100
                    result["mom_pct"] = round(mom, 3)

            if len(observations) >= 13:
                prev_year = observations[-13]
                prev_y_val = prev_year.get(BOC_SERIES["total_cpi"], {}).get("v")
                if prev_y_val and latest_val:
                    yoy = ((float(latest_val) / float(prev_y_val)) - 1) * 100
                    result["yoy_pct"] = round(yoy, 3)

        # Fetch core measures
        for key in ("cpi_trim", "cpi_median", "cpi_common"):
            try:
                url = f"{BOC_BASE_URL}/{BOC_SERIES[key]}/json?recent=1"
                core_data = fetch_json(url)
                core_obs = core_data.get("observations", [])
                if core_obs:
                    val = core_obs[-1].get(BOC_SERIES[key], {}).get("v")
                    if val is not None:
                        result[key] = float(val)
            except Exception:
                pass  # Core measures are optional

    except Exception:
        pass  # Return defaults on failure

    return result
