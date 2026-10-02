from datetime import datetime

from market_farm.regime_context import inflation_context


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
