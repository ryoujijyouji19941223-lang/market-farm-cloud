from market_farm import evaluate_reaction_oos as module


def _event(event_id, when, ret):
    return {
        "release_event_id": event_id,
        "actual_available_at": when,
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "stronger_growth",
        "surprise_direction": "ABOVE",
        "reactions": {
            "sp500": {
                "status": "OK",
                "preferred_measure": "return",
                "horizons": {
                    h: {"return": ret, "available_at": "2026-06-02T20:00:00+00:00"}
                    for h in ("1d", "2d", "5d", "20d")
                },
            }
        },
    }


def _prediction(pid, event_id, model, prob, horizon="1d"):
    return {
        "prediction_id": pid,
        "policy_epoch": 1,
        "immutable": True,
        "frozen_at": "2026-06-01T13:00:00+00:00",
        "release_event_id": event_id,
        "model": model,
        "source_id": "sp500",
        "horizon": horizon,
        "prob_positive": prob,
        "sample_count": 5,
        "similarity_tier": "SURPRISE_ONLY",
    }


def _policy():
    return {
        "policy_epoch": 1,
        "locked_at": "2026-05-15T00:00:00+00:00",
        "default_model": "surprise_only_baseline",
        "challengers": ["hierarchical_regime", "surprise_magnitude"],
        "minimum_sample": 3,
    }


def test_oos_scores_only_frozen_post_lock_predictions():
    events = [
        _event("old", "2026-05-01T08:30:00-04:00", 0.01),
        _event("future", "2026-06-01T08:30:00-04:00", -0.01),
    ]
    predictions = [
        _prediction("p0", "old", "surprise_only_baseline", 0.8),
        _prediction("p1", "future", "surprise_only_baseline", 0.8),
        _prediction("p2", "future", "hierarchical_regime", 0.7),
    ]

    payload = module.build_oos_evaluation(
        events=events,
        policy=_policy(),
        predictions=predictions,
    )
    assert payload["scored_release_events"] == 1
    assert payload["status"] == "ACTIVE"
    assert payload["rows_scored"] == 2
    assert payload["scoring_source"] == "immutable_frozen_prediction_ledger"


def test_oos_ignores_nonimmutable_prediction():
    events = [
        _event("future", "2026-06-01T08:30:00-04:00", 0.01),
    ]
    prediction = _prediction(
        "p1", "future", "surprise_only_baseline", 0.8
    )
    prediction["immutable"] = False

    payload = module.build_oos_evaluation(
        events=events,
        policy=_policy(),
        predictions=[prediction],
    )
    assert payload["rows_scored"] == 0
    assert payload["status"] == "WAITING_NEW_RELEASES"


def test_oos_waits_for_outcome_after_prediction_is_frozen():
    events = []
    predictions = [
        _prediction("p1", "future", "surprise_only_baseline", 0.8),
    ]
    payload = module.build_oos_evaluation(
        events=events,
        policy=_policy(),
        predictions=predictions,
    )
    assert payload["rows_scored"] == 0
    assert payload["frozen_predictions"] == 1
    assert payload["waiting_prediction_rows"] == 1
    assert payload["status"] == "WAITING_OUTCOMES"


def test_oos_rejects_mismatched_model_specification():
    events = [
        _event("future", "2026-06-01T08:30:00-04:00", 0.01),
    ]
    policy = _policy()
    policy["model_specification_versions"] = {
        "surprise_only_baseline": "surprise_only_baseline/v1",
    }
    prediction = _prediction(
        "p1", "future", "surprise_only_baseline", 0.8
    )
    prediction["model_specification_version"] = "surprise_only_baseline/v0"

    payload = module.build_oos_evaluation(
        events=events,
        policy=policy,
        predictions=[prediction],
    )
    assert payload["rows_scored"] == 0
    assert payload["status"] == "WAITING_NEW_RELEASES"


def test_oos_excludes_predictions_frozen_after_outcome_or_before_release():
    events = [_event("future", "2026-06-01T08:30:00-04:00", .01)]
    late = _prediction("late", "future", "surprise_only_baseline", .8)
    late["frozen_at"] = "2026-06-03T00:00:00+00:00"
    early = _prediction("early", "future", "surprise_only_baseline", .8)
    early["frozen_at"] = "2026-05-31T00:00:00+00:00"
    payload = module.build_oos_evaluation(events=events, policy=_policy(), predictions=[late, early])
    assert payload["rows_scored"] == 0
    assert payload["excluded_timing_rows"] == 2


def test_oos_excludes_outcome_with_unknown_timestamp():
    event = _event("future", "2026-06-01T08:30:00-04:00", .01)
    del event["reactions"]["sp500"]["horizons"]["1d"]["available_at"]
    payload = module.build_oos_evaluation(events=[event], policy=_policy(), predictions=[_prediction("p", "future", "surprise_only_baseline", .8)])
    assert payload["rows_scored"] == 0
    assert payload["excluded_timing_rows"] == 1
