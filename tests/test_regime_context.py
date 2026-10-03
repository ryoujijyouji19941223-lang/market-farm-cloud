from datetime import datetime

from market_farm.regime_context import inflation_context, regime_signature


def _row(period, available_at, value, indicator="US_CPI_MOM_GROWTH"):
    return {
        "record_id": f"{indicator}:{period}",
        "event_key": f"{indicator}:{period}",
        "indicator": indicator,
        "observation_period": period,
        "value": value,
        "unit": "percent",
        "release_number": 1,
        "information_tier": "public_realtime",
        "available_at": available_at,
        "availability_precision": "conservative_vintage_month_end",
        "release_date_provenance": "test",
        "transformation": "mom_annualized_percent",
    }


def test_inflation_context_uses_only_information_strictly_before_cutoff():
    rows = [
        _row("2025M01", "2025-02-28T23:59:59-05:00", 1.0),
        _row("2025M02", "2025-03-31T23:59:59-04:00", 2.0),
        _row("2025M03", "2025-04-30T23:59:59-04:00", 3.0),
        _row("2025M04", "2025-05-31T23:59:59-04:00", 4.0),
        _row("2025M05", "2025-06-30T23:59:59-04:00", 5.0),
        _row("2025M06", "2025-07-31T23:59:59-04:00", 6.0),
        # Exactly at cutoff: must not leak into pre-release context.
        _row("2025M07", "2025-08-31T23:59:59-04:00", 99.0),
    ]
    cutoff = datetime.fromisoformat("2025-08-31T23:59:59-04:00")
    out = inflation_context(cutoff, rows)
    headline = out["headline_cpi"]

    assert headline["observations"] == 6
    assert headline["latest_value"] == 6.0
    assert headline["recent_3m_median"] == 5.0
    assert headline["previous_3m_median"] == 2.0
    assert headline["three_month_momentum"] == 3.0
    assert 0.0 <= headline["expanding_percentile"] <= 1.0


def test_inflation_context_does_not_use_unresolved_or_future_rows():
    rows = [
        _row("2025M01", "2025-02-28T23:59:59-05:00", 1.0),
        {
            **_row("2025M02", "2025-03-31T23:59:59-04:00", 2.0),
            "information_tier": "unresolved_release_time",
        },
        _row("2025M03", "2026-04-30T23:59:59-04:00", 3.0),
    ]
    cutoff = datetime.fromisoformat("2025-12-31T23:59:59-05:00")
    out = inflation_context(cutoff, rows)
    assert out["headline_cpi"]["observations"] == 1
    assert out["headline_cpi"]["latest_value"] == 1.0



def test_regime_signature_uses_point_in_time_percentiles():
    rows = []
    values = [1.0, 1.2, 1.5, 2.0, 2.4, 3.0, 3.4, 3.8, 4.1]
    for i, value in enumerate(values, 1):
        rows.append(_row(
            f"2025M{i:02d}",
            f"2025-{min(i + 1, 12):02d}-28T23:59:59-05:00",
            value,
        ))
        rows.append(_row(
            f"2025M{i:02d}",
            f"2025-{min(i + 1, 12):02d}-28T23:59:59-05:00",
            value - 0.2,
            indicator="US_CORE_CPI_MOM_GROWTH",
        ))

    cutoff = datetime.fromisoformat("2025-12-31T23:59:59-05:00")
    context = inflation_context(cutoff, rows)
    signature = regime_signature(context)

    assert signature["quality"] == "FULL"
    assert signature["headline_level"] == "high"
    assert signature["headline_momentum"] in {"mixed", "heating"}
    assert signature["core_level"] == "high"
    assert signature["causal_claim"] is None


def test_regime_signature_marks_missing_context():
    context = {
        "headline_cpi": {"status": "NO_POINT_IN_TIME_DATA"},
        "core_cpi": {"status": "NO_POINT_IN_TIME_DATA"},
    }
    signature = regime_signature(context)
    assert signature["quality"] == "MISSING"
    assert signature["headline_level"] is None
    assert signature["core_level"] is None
