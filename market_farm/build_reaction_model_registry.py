from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BACKTEST = Path("data/market_experience/analog_backtest.json")
OUT = Path("data/market_experience/reaction_model_registry.json")


def build_registry(backtest: dict) -> dict:
    paired = backtest.get("paired_comparison", {})
    weighted_n = 0
    weighted_diff = 0.0
    better = 0
    worse = 0
    ties = 0

    for row in paired.values():
        n = int(row.get("paired_predictions", 0))
        diff = row.get("brier_difference_hierarchical_minus_baseline")
        if diff is None or n <= 0:
            continue
        diff = float(diff)
        weighted_n += n
        weighted_diff += n * diff
        if diff < 0:
            better += 1
        elif diff > 0:
            worse += 1
        else:
            ties += 1

    mean_diff = (
        weighted_diff / weighted_n
        if weighted_n else None
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "default_model": "surprise_only_baseline",
        "models": {
            "surprise_only_baseline": {
                "role": "default",
                "status": "ACTIVE_REFERENCE",
                "description": (
                    "Post-release analogs matched by indicator and surprise "
                    "direction/semantic effect only."
                ),
            },
            "hierarchical_regime": {
                "role": "challenger",
                "status": "RESEARCH_ONLY",
                "description": (
                    "Adds point-in-time headline inflation regime similarity "
                    "with hierarchical fallback."
                ),
                "paired_prediction_cells": weighted_n,
                "market_horizon_cells_better": better,
                "market_horizon_cells_worse": worse,
                "market_horizon_cells_tied": ties,
                "weighted_brier_difference_vs_default": mean_diff,
                "interpretation": (
                    "negative is better than default; positive is worse"
                ),
            },
        },
        "automatic_promotion_enabled": False,
        "promotion_policy": (
            "Do not promote a challenger using the same historical sample used "
            "to design it. Keep challengers research-only until an independently "
            "locked out-of-sample evaluation is available."
        ),
        "live_use_note": (
            "This registry controls research model status only. It does not "
            "constitute a trading recommendation."
        ),
    }


def main():
    if not BACKTEST.exists():
        raise RuntimeError("analog backtest is missing")
    payload = json.loads(BACKTEST.read_text(encoding="utf-8"))
    registry = build_registry(payload)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "default_model": registry["default_model"],
        "challenger_status": (
            registry["models"]["hierarchical_regime"]["status"]
        ),
        "weighted_brier_difference": (
            registry["models"]["hierarchical_regime"]
            ["weighted_brier_difference_vs_default"]
        ),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
