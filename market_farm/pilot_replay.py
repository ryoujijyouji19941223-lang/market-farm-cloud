from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .replay_backfill import replay_month, month_start, previous_month
from .research_report import build_report
from .decision import forecast_qualification
from .point_in_time import assert_snapshot_metadata, assert_articles_cutoff

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
    outputs = []
    for m in months:
        saved = Path("data/replay") / f"{m.strftime('%Y-%m')}.json"
        if saved.exists():
            data = json.loads(saved.read_text(encoding="utf-8"))
            for asset in data.get("assets", {}).values():
                for snap in asset.get("snapshots", []):
                    assert_snapshot_metadata(snap)
                    cutoff = datetime.fromisoformat(snap["information_cutoff_jst"])
                    assert_articles_cutoff(snap.get("asset_news_examples", []), cutoff, "saved asset news")
                    assert_articles_cutoff(snap.get("world_news_examples", []), cutoff, "saved world news")
                    snap["forecast_qualification"] = forecast_qualification(
                        snap.get("prediction_probability_up", 0.5),
                        snap.get("price_score", 0.0),
                        snap.get("news_score", 0.0),
                        snap.get("macro_score", 0.0),
                    )
            outputs.append(data)
        else:
            outputs.append(replay_month(m))
    result = {
        "experiment": "three_month_point_in_time_pilot",
        "months": [m.strftime("%Y-%m") for m in months],
        "rule": "Only information available by each snapshot cutoff may enter prediction features.",
        "source_mode": "reuse_saved_replay_when_available",
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
