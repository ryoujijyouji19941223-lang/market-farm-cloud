from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BACKTEST = Path("data/market_experience/analog_backtest.json")
OUT = Path("data/market_experience/reaction_model_registry.json")


def _comparison_metrics(comparison: dict) -> dict:
    weighted_n = 0
    weighted_diff = 0.0
    better = 0
    worse = 0
    ties = 0

    for row in comparison.values():
        n = int(row.get("paired_predictions", 0))
        diff = row.get("brier_difference_challenger_minus_baseline")
        if diff is None:
            # Backward compatibility with the first regime backtest format.
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

    return {
        "paired_prediction_cells": weighted_n,
        "market_horizon_cells_better": better,
        "market_horizon_cells_worse": worse,
        "market_horizon_cells_tied": ties,
        "weighted_brier_difference_vs_default": (
            weighted_diff / weighted_n if weighted_n else None
        ),
    }


def build_registry(backtest: dict) -> dict:
    regime_metrics = _comparison_metrics(
        backtest.get("paired_comparison", {})
    )
    magnitude_metrics = _comparison_metrics(
        backtest.get("magnitude_paired_comparison", {})
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
                **regime_metrics,
                "interpretation": (
                    "negative Brier difference is better than default"
                ),
            },
            "surprise_magnitude": {
                "role": "challenger",
                "status": "RESEARCH_ONLY",
                "description": (
                    "Adds point-in-time surprise magnitude bucket similarity "
                    "with fallback to the default surprise-only analog set."
                ),
                **magnitude_metrics,
                "interpretation": (
                    "negative Brier difference is better than default"
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
        "regime_status": registry["models"]["hierarchical_regime"]["status"],
        "magnitude_status": registry["models"]["surprise_magnitude"]["status"],
        "regime_brier_difference": (
            registry["models"]["hierarchical_regime"]
            ["weighted_brier_difference_vs_default"]
        ),
        "magnitude_brier_difference": (
            registry["models"]["surprise_magnitude"]
            ["weighted_brier_difference_vs_default"]
        ),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
