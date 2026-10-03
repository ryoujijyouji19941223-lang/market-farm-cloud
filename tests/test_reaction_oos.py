from market_farm import evaluate_reaction_oos as module


def _event(event_id, when, ret):
    return {
        "release_event_id": event_id,
        "actual_available_at": when,
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "stronger_growth",
        "surprise_direction": "ABOVE",
        "pre_release_context": {
            "regime_signature": {
                "headline_level": "high",
                "headline_momentum": "heating",
            }
        },
        "post_release_context": {
            "surprise_magnitude": {
                "magnitude_bucket": "large",
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


def test_oos_scores_only_events_after_lock():
    events = [
        _event("a", "2026-01-01T08:30:00-05:00", 0.01),
        _event("b", "2026-02-01T08:30:00-05:00", 0.02),
        _event("c", "2026-03-01T08:30:00-05:00", 0.03),
        _event("d", "2026-04-01T08:30:00-04:00", 0.01),
        _event("e", "2026-05-01T08:30:00-04:00", 0.02),
        _event("future", "2026-06-01T08:30:00-04:00", -0.01),
    ]
    policy = {
        "policy_epoch": 1,
        "locked_at": "2026-05-15T00:00:00+00:00",
        "default_model": "surprise_only_baseline",
        "challengers": ["hierarchical_regime", "surprise_magnitude"],
        "minimum_sample": 3,
    }

    payload = module.build_oos_evaluation(
        events=events,
        policy=policy,
    )
    assert payload["scored_release_events"] == 1
    assert payload["status"] == "ACTIVE"
    assert payload["policy_epoch"] == 1


def test_oos_waits_when_no_new_release():
    events = [
        _event("a", "2026-01-01T08:30:00-05:00", 0.01),
    ]
    policy = {
        "policy_epoch": 1,
        "locked_at": "2026-05-15T00:00:00+00:00",
        "default_model": "surprise_only_baseline",
        "challengers": ["hierarchical_regime", "surprise_magnitude"],
        "minimum_sample": 1,
    }
    payload = module.build_oos_evaluation(
        events=events,
        policy=policy,
    )
    assert payload["scored_release_events"] == 0
    assert payload["status"] == "WAITING_NEW_RELEASES"
    assert payload["rows_scored"] == 0
