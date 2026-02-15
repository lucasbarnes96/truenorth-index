from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    latest_path = Path("data/latest.json")
    if not latest_path.exists():
        print("Gate check failed: data/latest.json not found.")
        return 1

    payload = json.loads(latest_path.read_text())
    release = payload.get("release", {})
    status = release.get("status")
    blocked = release.get("blocked_conditions", [])

    print(f"Release status: {status}")
    if blocked:
        print("Blocked conditions:")
        for reason in blocked:
            print(f"- {reason}")

    if status != "published":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
