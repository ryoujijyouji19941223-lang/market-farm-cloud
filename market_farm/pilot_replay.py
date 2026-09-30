from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .replay_backfill import replay_month, month_start, previous_month
from .research_report import build_report

JST = ZoneInfo("Asia/Tokyo")
OUT = Path("data/pilot_3month.json")


def pilot_months(now=None):
    now = now or datetime.now(JST)
    latest = previous_month(month_start(now))
    middle = previous_month(latest)
    oldest = previous_month(middle)
    return [oldest, middle, latest]


def summarize(outputs):
    rows = []
    for month in outputs:
        for symbol, asset in month.get("assets", {}).items():
            for snap in asset.get("snapshots", []):
                outcome = (snap.get("horizons") or {}).get("next_day")
                if not outcome:
                    continue
                decision = (snap.get("forecast_qualification") or {}).get("decision", "FORECAST")
                rows.append({
                    "symbol": symbol,
                    "decision": decision,
                    "correct": snap.get("prediction_direction") == outcome.get("direction"),
                })

    forecasted = [r for r in rows if r["decision"] == "FORECAST"]
    abstained = [r for r in rows if r["decision"] == "ABSTAIN"]
    correct = sum(r["correct"] for r in forecasted)
    return {
        "observations": len(rows),
        "forecasted": len(forecasted),
        "abstained": len(abstained),
        "coverage": len(forecasted) / len(rows) if rows else None,
        "forecast_accuracy": correct / len(forecasted) if forecasted else None,
        "forecast_correct": correct,
    }


def run():
    months = pilot_months()
    outputs = [replay_month(m) for m in months]
    result = {
        "experiment": "three_month_point_in_time_pilot",
        "months": [m.strftime("%Y-%m") for m in months],
        "rule": "Only information available by each snapshot cutoff may enter prediction features.",
        "summary": summarize(outputs),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    build_report()
    return result


def main():
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
