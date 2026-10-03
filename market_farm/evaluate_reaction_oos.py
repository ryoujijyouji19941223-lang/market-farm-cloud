from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .backtest_analog_reactions import (
    HORIZONS,
    MARKETS,
    _actual_value,
    _broad_report,
    _score_probability,
)
from .experience_query import (
    analog_report_for_release_event,
    analog_report_for_release_event_magnitude,
    load_release_events,
)

POLICY = Path("data/market_experience/reaction_oos_policy.json")
OUT = Path("data/market_experience/reaction_oos_evaluation.json")


def _model_reports(event: dict, events: list[dict], min_samples: int) -> dict:
    return {
        "surprise_only_baseline": _broad_report(
            event, events, min_samples
        ),
        "hierarchical_regime": analog_report_for_release_event(
            event, events=events, min_samples=min_samples
        ),
        "surprise_magnitude": analog_report_for_release_event_magnitude(
            event, events=events, min_samples=min_samples
        ),
    }


def build_oos_evaluation(
    *,
    events: list[dict] | None = None,
    policy: dict | None = None,
) -> dict:
    events = load_release_events() if events is None else events
    if policy is None:
        if not POLICY.exists():
            raise RuntimeError("OOS policy lock is missing")
        policy = json.loads(POLICY.read_text(encoding="utf-8"))

    locked_at = datetime.fromisoformat(policy["locked_at"])
    if locked_at.tzinfo is None:
        raise ValueError("locked_at must be timezone-aware")
    min_samples = int(policy["minimum_sample"])

    scored_events = []
    for event in events:
        released = datetime.fromisoformat(event["actual_available_at"])
        if released.tzinfo is None:
            continue
        if released > locked_at:
            scored_events.append(event)

    rows = []
    for event in scored_events:
        reports = _model_reports(event, events, min_samples)
        for model_name, report in reports.items():
            for source_id in MARKETS:
                for horizon in HORIZONS:
                    actual = _actual_value(event, source_id, horizon)
                    if actual is None:
                        continue
                    summary = (
                        report.get("markets", {})
                        .get(source_id, {})
                        .get(horizon, {})
                    )
                    if summary.get("status") != "OK":
                        continue
                    prob = summary.get("positive_share")
                    if prob is None:
                        continue
                    rows.append({
                        "model": model_name,
                        "release_event_id": event.get("release_event_id"),
                        "actual_available_at": event.get("actual_available_at"),
                        "source_id": source_id,
                        "horizon": horizon,
                        "similarity_tier": report.get("similarity_tier"),
                        "sample_count": summary.get("sample_count"),
                        "actual_value": actual,
                        **_score_probability(float(prob), actual),
                    })

    by_key = defaultdict(list)
    for row in rows:
        by_key[(row["model"], row["source_id"], row["horizon"])].append(row)

    summaries = []
    for (model, source_id, horizon), group in sorted(by_key.items()):
        directional = [
            x for x in group
            if x["directional_correct"] is not None
        ]
        summaries.append({
            "model": model,
            "source_id": source_id,
            "horizon": horizon,
            "predictions": len(group),
            "mean_brier": statistics.fmean(
                [x["brier"] for x in group]
            ) if group else None,
            "directional_predictions": len(directional),
            "directional_accuracy": (
                sum(bool(x["directional_correct"]) for x in directional)
                / len(directional)
                if directional else None
            ),
        })

    keyed = defaultdict(dict)
    for row in rows:
        key = (row["release_event_id"], row["source_id"], row["horizon"])
        keyed[key][row["model"]] = row

    paired = {}
    baseline = policy["default_model"]
    for challenger in policy.get("challengers", []):
        cells = [
            models for models in keyed.values()
            if {baseline, challenger}.issubset(models)
        ]
        b0 = [x[baseline]["brier"] for x in cells]
        bc = [x[challenger]["brier"] for x in cells]
        paired[challenger] = {
            "paired_predictions": len(cells),
            "baseline_mean_brier": (
                statistics.fmean(b0) if b0 else None
            ),
            "challenger_mean_brier": (
                statistics.fmean(bc) if bc else None
            ),
            "brier_difference_challenger_minus_baseline": (
                statistics.fmean(bc) - statistics.fmean(b0)
                if b0 and bc else None
            ),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_epoch": policy["policy_epoch"],
        "locked_at": policy["locked_at"],
        "status": (
            "ACTIVE" if scored_events else "WAITING_NEW_RELEASES"
        ),
        "scored_release_events": len(scored_events),
        "rows_scored": len(rows),
        "summaries": summaries,
        "paired_comparison": paired,
        "promotion_automatic": False,
        "note": (
            "Strict out-of-sample ledger. Only release events after the immutable "
            "epoch lock are scored. Historical pre-lock events may be used as "
            "prior analog memory but never as OOS score rows."
        ),
    }


def main():
    payload = build_oos_evaluation()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "policy_epoch": payload["policy_epoch"],
        "status": payload["status"],
        "scored_release_events": payload["scored_release_events"],
        "rows_scored": payload["rows_scored"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
