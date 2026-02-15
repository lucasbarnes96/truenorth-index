from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "TrueNorthIndexBot/1.0 (+https://github.com/)"


class FetchError(Exception):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS, retries: int = 2) -> str:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as err:  # pragma: no cover - network dependent
            last_err = err
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"Failed to fetch URL: {url}: {last_err}")


def fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS, retries: int = 2) -> Any:
    text = fetch_url(url, timeout=timeout, retries=retries)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"Invalid JSON from {url}: {exc}") from exc


def parse_floats_from_text(text: str) -> list[float]:
    candidates = re.findall(r"(?<!\d)(\d{1,4}(?:\.\d{1,4})?)(?!\d)", text)
    values: list[float] = []
    for value in candidates:
        try:
            values.append(float(value))
        except ValueError:
            continue
    return values
