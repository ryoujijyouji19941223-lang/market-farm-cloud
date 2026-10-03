from market_farm import backtest_analog_reactions as module


def _event(event_id, year, ret, level="high", momentum="heating"):
    return {
        "release_event_id": event_id,
        "actual_available_at": f"{year}-01-15T08:30:00-05:00",
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "stronger_growth",
        "surprise_direction": "ABOVE",
        "pre_release_context": {
            "regime_signature": {
                "headline_level": level,
                "headline_momentum": momentum,
            }
        },
        "reactions": {
            "sp500": {
                "status": "OK",
                "preferred_measure": "return",
                "data_provider": "yfinance",
                "fallback": False,
                "horizons": {
                    "1d": {"return": ret},
                    "2d": {"return": ret},
                    "5d": {"return": ret},
                    "20d": {"return": ret},
                },
            }
        },
    }


def test_probability_score():
    score = module._score_probability(0.75, 0.02)
    assert score["predicted_direction"] == "UP"
    assert score["directional_correct"] is True
    assert score["brier"] == 0.0625


def test_backtest_is_walk_forward(monkeypatch):
    events = [
        _event("a", 2001, 0.01),
        _event("b", 2002, 0.02),
        _event("c", 2003, -0.01),
        _event("d", 2004, 0.03),
    ]
    monkeypatch.setattr(module, "load_release_events", lambda: events)

    payload = module.build_backtest(min_samples=2)
    sp500_1d = [
        row for row in payload["summaries"]
        if row["source_id"] == "sp500" and row["horizon"] == "1d"
    ]
    assert sp500_1d
    # The first two releases cannot be scored with two prior analogs.
    assert all(row["predictions"] <= 2 for row in sp500_1d)
    assert payload["rows_scored"] > 0
