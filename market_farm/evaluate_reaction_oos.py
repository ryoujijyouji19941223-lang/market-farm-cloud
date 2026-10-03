from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .backtest_analog_reactions import _actual_value, _score_probability
from .experience_query import load_release_events

POLICY = Path("data/market_experience/reaction_oos_policy.json")
PREDICTIONS = Path("data/market_experience/reaction_oos_predictions.jsonl")
OUT = Path("data/market_experience/reaction_oos_evaluation.json")


def _load_frozen_predictions(epoch: int) -> list[dict]:
    if not PREDICTIONS.exists():
        return []
    out = []
    for line in PREDICTIONS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if int(row.get("policy_epoch", -1)) != epoch:
            continue
        if row.get("immutable") is not True:
            continue
        out.append(row)
    return out


def build_oos_evaluation(
    *,
    events: list[dict] | None = None,
    policy: dict | None = None,
    predictions: list[dict] | None = None,
) -> dict:
    events = load_release_events() if events is None else events
    if policy is None:
        if not POLICY.exists():
            raise RuntimeError("OOS policy lock is missing")
        policy = json.loads(POLICY.read_text(encoding="utf-8"))

    epoch = int(policy["policy_epoch"])
    locked_at = datetime.fromisoformat(policy["locked_at"])
    if locked_at.tzinfo is None:
        raise ValueError("locked_at must be timezone-aware")

    predictions = (
        _load_frozen_predictions(epoch)
        if predictions is None else predictions
    )
    event_map = {
        event.get("release_event_id"): event
        for event in events
        if event.get("release_event_id")
    }

    rows = []
    scored_event_ids = set()
    waiting_predictions = 0

    versions = policy.get("model_specification_versions", {})

    for prediction in predictions:
        if int(prediction.get("policy_epoch", -1)) != epoch:
            continue
        if prediction.get("immutable") is not True:
            continue
        expected_version = versions.get(prediction.get("model"))
        if expected_version is not None:
            if prediction.get("model_specification_version") != expected_version:
                continue

        event = event_map.get(prediction.get("release_event_id"))
        if event is None:
            waiting_predictions += 1
            continue

        released = datetime.fromisoformat(event["actual_available_at"])
        if released.tzinfo is None or released <= locked_at:
            continue

        actual = _actual_value(
            event,
            prediction["source_id"],
            prediction["horizon"],
        )
        if actual is None:
            waiting_predictions += 1
            continue

        prob = prediction.get("prob_positive")
        if prob is None:
            continue

        rows.append({
            "prediction_id": prediction["prediction_id"],
            "policy_epoch": epoch,
            "frozen_at": prediction.get("frozen_at"),
            "model": prediction["model"],
            "release_event_id": event["release_event_id"],
            "actual_available_at": event["actual_available_at"],
            "source_id": prediction["source_id"],
            "horizon": prediction["horizon"],
            "similarity_tier": prediction.get("similarity_tier"),
            "sample_count": prediction.get("sample_count"),
            "actual_value": actual,
            **_score_probability(float(prob), actual),
        })
        scored_event_ids.add(event["release_event_id"])

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
            "baseline_mean_brier": statistics.fmean(b0) if b0 else None,
            "challenger_mean_brier": statistics.fmean(bc) if bc else None,
            "brier_difference_challenger_minus_baseline": (
                statistics.fmean(bc) - statistics.fmean(b0)
                if b0 and bc else None
            ),
        }

    def _valid_frozen_prediction(x: dict) -> bool:
        if int(x.get("policy_epoch", -1)) != epoch:
            return False
        if x.get("immutable") is not True:
            return False
        expected_version = versions.get(x.get("model"))
        if expected_version is not None:
            return x.get("model_specification_version") == expected_version
        return True

    frozen_count = sum(
        1 for x in predictions
        if _valid_frozen_prediction(x)
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy_epoch": epoch,
        "locked_at": policy["locked_at"],
        "status": (
            "ACTIVE"
            if rows
            else (
                "WAITING_OUTCOMES"
                if frozen_count
                else "WAITING_NEW_RELEASES"
            )
        ),
        "frozen_predictions": frozen_count,
        "scored_release_events": len(scored_event_ids),
        "rows_scored": len(rows),
        "waiting_prediction_rows": waiting_predictions,
        "summaries": summaries,
        "paired_comparison": paired,
        "promotion_automatic": False,
        "scoring_source": "immutable_frozen_prediction_ledger",
        "model_specification_versions": versions,
        "note": (
            "Strict OOS ledger. Model probabilities are frozen on first ingestion "
            "of a post-lock release and are never recomputed for scoring. Market "
            "outcomes are attached later when available."
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
        "frozen_predictions": payload["frozen_predictions"],
        "scored_release_events": payload["scored_release_events"],
        "rows_scored": payload["rows_scored"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
