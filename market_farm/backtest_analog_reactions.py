from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .experience_query import (
    analog_report,
    analog_report_for_release_event,
    load_release_events,
)

OUT = Path("data/market_experience/analog_backtest.json")
MARKETS = ("sp500", "gold_futures", "usd_jpy", "us10y")
HORIZONS = ("1d", "2d", "5d", "20d")


def _actual_value(event: dict, source_id: str, horizon: str) -> float | None:
    reaction = (event.get("reactions") or {}).get(source_id) or {}
    if reaction.get("status") != "OK":
        return None
    point = (reaction.get("horizons") or {}).get(horizon)
    if not point:
        return None
    preferred = reaction.get("preferred_measure", "return")
    if preferred == "change_bps":
        value = point.get("change_bps")
    else:
        value = point.get("return")
    return None if value is None else float(value)


def _score_probability(prob_positive: float, actual_value: float) -> dict:
    actual_positive = 1.0 if actual_value > 0 else 0.0
    if prob_positive > 0.5:
        direction = "UP"
        correct = actual_value > 0
    elif prob_positive < 0.5:
        direction = "DOWN"
        correct = actual_value < 0
    else:
        direction = "FLAT"
        correct = None
    return {
        "actual_positive": bool(actual_positive),
        "prob_positive": prob_positive,
        "brier": (prob_positive - actual_positive) ** 2,
        "predicted_direction": direction,
        "directional_correct": correct,
    }


def _broad_report(event: dict, events: list[dict], min_samples: int) -> dict:
    cutoff = datetime.fromisoformat(event["actual_available_at"])
    report = analog_report(
        cutoff=cutoff,
        indicator=event["indicator"],
        semantic_effect=event.get("semantic_effect"),
        surprise_direction=event.get("surprise_direction"),
        regime_filters={},
        min_samples=min_samples,
        events=events,
    )
    report["similarity_tier"] = "SURPRISE_ONLY"
    return report


def build_backtest(min_samples: int = 5) -> dict:
    events = load_release_events()
    rows = []

    for event in events:
        hierarchical = analog_report_for_release_event(
            event,
            events=events,
            min_samples=min_samples,
        )
        broad = _broad_report(event, events, min_samples)

        for model_name, report in (
            ("hierarchical_regime", hierarchical),
            ("surprise_only_baseline", broad),
        ):
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
                    score = _score_probability(float(prob), actual)
                    rows.append({
                        "model": model_name,
                        "release_event_id": event.get("release_event_id"),
                        "actual_available_at": event.get("actual_available_at"),
                        "source_id": source_id,
                        "horizon": horizon,
                        "similarity_tier": report.get("similarity_tier"),
                        "sample_count": summary.get("sample_count"),
                        "fallback_share": summary.get("fallback_share"),
                        "actual_value": actual,
                        **score,
                    })

    by_key = defaultdict(list)
    for row in rows:
        by_key[(row["model"], row["source_id"], row["horizon"])].append(row)

    summaries = []
    for (model, source_id, horizon), group in sorted(by_key.items()):
        briers = [x["brier"] for x in group]
        directional = [
            x for x in group
            if x["directional_correct"] is not None
        ]
        tier_counts = Counter(x.get("similarity_tier") or "NONE" for x in group)
        summaries.append({
            "model": model,
            "source_id": source_id,
            "horizon": horizon,
            "predictions": len(group),
            "mean_brier": statistics.fmean(briers) if briers else None,
            "directional_predictions": len(directional),
            "directional_accuracy": (
                sum(bool(x["directional_correct"]) for x in directional)
                / len(directional)
                if directional else None
            ),
            "flat_probability_count": len(group) - len(directional),
            "similarity_tier_counts": dict(tier_counts),
        })

    # Fair model comparison: only event/market/horizon cells scored by both.
    keyed = defaultdict(dict)
    for row in rows:
        key = (row["release_event_id"], row["source_id"], row["horizon"])
        keyed[key][row["model"]] = row

    paired = [
        models for models in keyed.values()
        if {"hierarchical_regime", "surprise_only_baseline"}.issubset(models)
    ]
    paired_summary = {}
    for source_id in MARKETS:
        for horizon in HORIZONS:
            subset = [
                pair for pair in paired
                if pair["hierarchical_regime"]["source_id"] == source_id
                and pair["hierarchical_regime"]["horizon"] == horizon
            ]
            if not subset:
                continue
            hb = [x["hierarchical_regime"]["brier"] for x in subset]
            bb = [x["surprise_only_baseline"]["brier"] for x in subset]
            paired_summary[f"{source_id}:{horizon}"] = {
                "paired_predictions": len(subset),
                "hierarchical_mean_brier": statistics.fmean(hb),
                "baseline_mean_brier": statistics.fmean(bb),
                "brier_difference_hierarchical_minus_baseline": (
                    statistics.fmean(hb) - statistics.fmean(bb)
                ),
            }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minimum_sample": min_samples,
        "release_events": len(events),
        "rows_scored": len(rows),
        "summaries": summaries,
        "paired_comparison": paired_summary,
        "note": (
            "Walk-forward post-release reaction backtest. Each prediction uses "
            "only earlier release events. Lower Brier score is better. "
            "This measures historical association, not causal effect or trading profit."
        ),
    }


def main():
    payload = build_backtest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "release_events": payload["release_events"],
        "rows_scored": payload["rows_scored"],
        "paired_cells": len(payload["paired_comparison"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
