from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Importing registers the verified collectors.
from . import collectors_rss  # noqa: F401
from .official_collectors import run_collectors

UTC = ZoneInfo("UTC")
STATUS = Path("data/official_archive/collector_status.json")


def main():
    report = run_collectors()
    report["generated_at"] = datetime.now(UTC).isoformat()
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
