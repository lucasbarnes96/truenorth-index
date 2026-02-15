from __future__ import annotations

import csv
import io
import urllib.request
import zipfile

from .common import USER_AGENT

STATCAN_CPI_ZIP = "https://www150.statcan.gc.ca/n1/en/tbl/csv/18100004-eng.zip"
ALL_ITEMS = "All-items"


def _download_zip_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def fetch_official_cpi_summary() -> dict:
    try:
        data = _download_zip_bytes(STATCAN_CPI_ZIP)
        if not zipfile.is_zipfile(io.BytesIO(data)):
            return {"latest_release_month": None, "mom_pct": None, "yoy_pct": None}

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            csv_name = next(name for name in zf.namelist() if name.endswith(".csv"))
            with zf.open(csv_name) as handle:
                decoded = io.TextIOWrapper(handle, encoding="utf-8-sig", errors="ignore")
                rows = list(csv.DictReader(decoded))

        candidates = [
            r
            for r in rows
            if r.get("GEO") == "Canada"
            and (r.get("Products and product groups") or "").strip() == ALL_ITEMS
            and r.get("VALUE")
            and r.get("REF_DATE")
        ]
        if len(candidates) < 13:
            return {"latest_release_month": None, "mom_pct": None, "yoy_pct": None}

        candidates.sort(key=lambda r: r["REF_DATE"])
        latest = candidates[-1]
        prev = candidates[-2]
        prev_year = candidates[-13]

        latest_v = float(latest["VALUE"])
        prev_v = float(prev["VALUE"])
        prev_y_v = float(prev_year["VALUE"])

        mom = ((latest_v / prev_v) - 1) * 100 if prev_v else None
        yoy = ((latest_v / prev_y_v) - 1) * 100 if prev_y_v else None

        return {
            "latest_release_month": latest["REF_DATE"],
            "mom_pct": round(mom, 3) if mom is not None else None,
            "yoy_pct": round(yoy, 3) if yoy is not None else None,
        }
    except Exception:  # pragma: no cover - network dependent
        return {"latest_release_month": None, "mom_pct": None, "yoy_pct": None}
