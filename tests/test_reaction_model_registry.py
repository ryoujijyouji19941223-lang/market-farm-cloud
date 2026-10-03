from market_farm.build_reaction_model_registry import build_registry


def test_regime_challenger_is_not_auto_promoted():
    payload = {
        "paired_comparison": {
            "sp500:1d": {
                "paired_predictions": 100,
                "brier_difference_hierarchical_minus_baseline": -0.01,
            },
            "sp500:5d": {
                "paired_predictions": 100,
                "brier_difference_hierarchical_minus_baseline": 0.02,
            },
        }
    }
    registry = build_registry(payload)
    assert registry["default_model"] == "surprise_only_baseline"
    assert registry["models"]["hierarchical_regime"]["status"] == "RESEARCH_ONLY"
    assert registry["automatic_promotion_enabled"] is False
