from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .actual_archive import load_rows
from .backtest_analog_reactions import HORIZONS, MARKETS, _broad_report
from .build_experience_pairs import build_pairs
from .expectation_memory import load_all_expectations
from .experience_query import (
    analog_report_for_release_event,
    analog_report_for_release_event_magnitude,
    load_release_events,
)
from .indicator_semantics import describe_surprise
from .regime_context import inflation_context

POLICY = Path("data/market_experience/reaction_oos_policy.json")
STORE = Path("data/market_experience/reaction_oos_predictions.jsonl")


def _prediction_id(epoch: int, release_event_id: str, model: str, source_id: str, horizon: str) -> str:
    raw = f"{epoch}|{release_event_id}|{model}|{source_id}|{horizon}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _surprise(expectation: dict, actual: dict) -> dict:
    expected = float(expectation["expected_value"])
    value = float(actual["value"])
    delta = value - expected
    direction = "ABOVE" if delta > 0 else ("BELOW" if delta < 0 else "INLINE")
    return describe_surprise(actual["indicator"], {
        "status": "OK",
        "direction": direction,
        "surprise": delta,
        "expected_value": expected,
        "actual_value": value,
        "unit": actual["unit"],
    })


def _magnitude_context(target: dict, history: list[dict]) -> dict:
    raw = target.get("surprise")
    if raw is None:
        return {
            "status": "NO_SURPRISE",
            "prior_sample_count": 0,
            "absolute_surprise": None,
            "expanding_percentile": None,
            "magnitude_bucket": None,
        }

    prior = []
    cutoff = datetime.fromisoformat(target["actual_available_at"])
    for event in history:
        if event.get("indicator") != target.get("indicator"):
            continue
        try:
            available = datetime.fromisoformat(event["actual_available_at"])
        except Exception:
            continue
        if available >= cutoff:
            continue
        value = event.get("surprise")
        if value is not None:
            prior.append(abs(float(value)))

    magnitude = abs(float(raw))
    percentile = (
        sum(x <= magnitude for x in prior) / len(prior)
        if prior else None
    )
    bucket = None
    if percentile is not None:
        bucket = "small" if percentile < 1 / 3 else (
            "middle" if percentile < 2 / 3 else "large"
        )
    return {
        "status": "OK" if len(prior) >= 5 else "PARTIAL_HISTORY",
        "prior_sample_count": len(prior),
        "absolute_surprise": magnitude,
        "expanding_percentile": percentile,
        "magnitude_bucket": bucket,
        "method": "absolute surprise rank versus strictly earlier releases",
    }


def _target_events_after_lock(policy: dict, history: list[dict]) -> list[dict]:
    expectations = {x["expectation_id"]: x for x in load_all_expectations()}
    actuals = {x["record_id"]: x for x in load_rows()}
    all_actual_rows = list(actuals.values())
    locked_at = datetime.fromisoformat(policy["locked_at"])

    grouped = {}
    for pair in build_pairs()["items"]:
        if pair.get("status") not in {"READY", "READY_SURPRISE_ONLY"}:
            continue
        actual = actuals.get(pair["actual_record_id"])
        if actual is None or not actual.get("available_at"):
            continue
        released = datetime.fromisoformat(actual["available_at"])
        if released <= locked_at:
            continue
        grouped.setdefault(actual["record_id"], []).append(pair)

    targets = []
    for actual_id, pairs in grouped.items():
        actual = actuals[actual_id]
        valid = [p for p in pairs if p["expectation_id"] in expectations]
        if not valid:
            continue
        latest_pair = max(valid, key=lambda p: p["expectation_available_at"])
        latest = expectations[latest_pair["expectation_id"]]
        surprise = _surprise(latest, actual)
        released = datetime.fromisoformat(actual["available_at"])

        target = {
            "release_event_id": actual_id,
            "event_key": actual["event_key"],
            "indicator": actual["indicator"],
            "observation_period": actual["observation_period"],
            "actual_available_at": actual["available_at"],
            "actual_value": actual["value"],
            "unit": actual["unit"],
            "latest_public_expectation_id": latest["expectation_id"],
            "latest_public_expectation_at": latest["available_at"],
            "latest_public_expectation_value": latest["expected_value"],
            "surprise": surprise.get("surprise"),
            "surprise_direction": surprise.get("direction"),
            "semantic_effect": surprise.get("semantic_effect"),
            "pre_release_context": {
                "inflation": inflation_context(released, all_actual_rows),
            },
            "post_release_context": {},
        }
        from .regime_context import regime_signature
        target["pre_release_context"]["regime_signature"] = regime_signature(
            target["pre_release_context"]["inflation"]
        )
        target["post_release_context"]["surprise_magnitude"] = _magnitude_context(
            target, history
        )
        targets.append(target)

    return sorted(targets, key=lambda x: x["actual_available_at"])


def _reports(target: dict, history: list[dict], min_samples: int) -> dict:
    return {
        "surprise_only_baseline": _broad_report(target, history, min_samples),
        "hierarchical_regime": analog_report_for_release_event(
            target, events=history, min_samples=min_samples
        ),
        "surprise_magnitude": analog_report_for_release_event_magnitude(
            target, events=history, min_samples=min_samples
        ),
    }


def _load_existing() -> dict[str, dict]:
    rows = {}
    if not STORE.exists():
        return rows
    for line in STORE.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            rows[row["prediction_id"]] = row
        except Exception:
            continue
    return rows


def freeze_predictions() -> dict:
    if not POLICY.exists():
        raise RuntimeError("OOS policy lock is missing")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    epoch = int(policy["policy_epoch"])
    min_samples = int(policy["minimum_sample"])
    history = load_release_events()
    existing = _load_existing()
    added = 0

    for target in _target_events_after_lock(policy, history):
        reports = _reports(target, history, min_samples)
        for model_name, report in reports.items():
            for source_id in MARKETS:
                for horizon in HORIZONS:
                    summary = (
                        report.get("markets", {})
                        .get(source_id, {})
                        .get(horizon, {})
                    )
                    if summary.get("status") != "OK":
                        continue
                    probability = summary.get("positive_share")
                    if probability is None:
                        continue
                    pid = _prediction_id(
                        epoch, target["release_event_id"], model_name, source_id, horizon
                    )
                    if pid in existing:
                        continue
                    existing[pid] = {
                        "prediction_id": pid,
                        "policy_epoch": epoch,
                        "frozen_at": datetime.now(timezone.utc).isoformat(),
                        "release_event_id": target["release_event_id"],
                        "actual_available_at": target["actual_available_at"],
                        "model": model_name,
                        "source_id": source_id,
                        "horizon": horizon,
                        "prob_positive": float(probability),
                        "sample_count": summary.get("sample_count"),
                        "similarity_tier": report.get("similarity_tier"),
                        "history_cutoff": target["actual_available_at"],
                        "immutable": True,
                    }
                    added += 1

    STORE.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        existing.values(),
        key=lambda x: (
            x["actual_available_at"], x["release_event_id"],
            x["model"], x["source_id"], x["horizon"]
        ),
    )
    STORE.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in ordered)
        + ("\n" if ordered else ""),
        encoding="utf-8",
    )
    return {
        "policy_epoch": epoch,
        "target_events_after_lock": len(_target_events_after_lock(policy, history)),
        "predictions_total": len(ordered),
        "predictions_added": added,
    }


def main():
    print(json.dumps(freeze_predictions(), ensure_ascii=False))


if __name__ == "__main__":
    main()
