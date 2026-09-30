from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .actual_archive import save_rows
from .experience_pairs import pair_index
from .rtds_vintage_collector import fetch_gdp_first_releases

STATUS = Path("data/actual_releases/backfill_status.json")
PAIRS = Path("data/market_experience/pairs.json")


def main():
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": {},
    }

    try:
        gdp = fetch_gdp_first_releases()
        saved = save_rows("rtds_routput_first", gdp)
        status["datasets"]["ROUTPUT"] = {
            "status": "ok",
            "rows": len(gdp),
            "saved": saved,
            "method": "first visible public vintage -> q/q annualized growth",
        }
    except Exception as exc:
        status["datasets"]["ROUTPUT"] = {
            "status": "fetch_error",
            "error": str(exc),
        }

    pairs = pair_index()
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    PAIRS.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"actual releases paired={len(pairs)} status={status['datasets']}")


if __name__ == "__main__":
    main()
