from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_farm.expectation_memory import make_expectation, save_expectations, visible_expectations, promote_expectation
from market_farm.indicator_semantics import describe_surprise


JST = ZoneInfo("Asia/Tokyo")


def test_expectation_must_precede_release():
    with pytest.raises(ValueError):
        make_expectation(
            event_key="US_CPI_2026_06",
            available_at="2026-07-14T22:00:00+09:00",
            scheduled_for="2026-07-14T21:30:00+09:00",
            indicator="US_CPI_YOY",
            jurisdiction="US",
            expected_value=2.7,
            unit="percent",
            source="test",
            source_url="https://example.test",
        )


def test_cpi_above_expectation_means_more_inflation():
    row = describe_surprise("US_CPI_YOY", {"status": "OK", "direction": "ABOVE"})
    assert row["semantic_effect"] == "more_inflation"
    assert "rates" in row["themes"]


def test_unemployment_above_expectation_means_weaker_labor():
    row = describe_surprise("US_UNEMPLOYMENT_RATE", {"status": "OK", "direction": "ABOVE"})
    assert row["semantic_effect"] == "weaker_labor"


def test_private_expectation_is_not_visible_to_replay(tmp_path, monkeypatch):
    monkeypatch.setattr("market_farm.expectation_memory.STORE", tmp_path)
    item = make_expectation(
        event_key="FOMC_TEST",
        available_at="2026-06-01T10:00:00+09:00",
        scheduled_for="2026-06-02T03:00:00+09:00",
        indicator="FED_POLICY_RATE",
        jurisdiction="US",
        expected_value=4.0,
        unit="percent",
        source="internal-survey",
        source_url="https://example.test",
        visibility="private_until_after_release",
    )
    save_expectations([item])
    rows = visible_expectations(
        datetime(2026, 6, 1, 0, 0, tzinfo=JST),
        datetime(2026, 6, 1, 23, 0, tzinfo=JST),
    )
    assert rows == []


def test_verified_release_promotes_quarantined_forecast():
    item = make_expectation(
        event_key="SPF:TEST:1991Q1",
        available_at="1991-02-28T23:59:00-05:00",
        scheduled_for="1991-03-31T23:59:00-05:00",
        indicator="US_REAL_GDP_GROWTH",
        jurisdiction="US",
        expected_value=2.0,
        unit="percent",
        source="SPF",
        source_url="https://example.test",
        visibility="quarantined_release_date_proxy",
    )
    row = item.__dict__.copy()
    fixed = promote_expectation(
        row,
        "1991-02-20T23:59:59-05:00",
        provenance="official_release_dates",
    )
    assert fixed["visibility"] == "public"
    assert fixed["available_at"] == "1991-02-20T23:59:59-05:00"


def test_quarantined_historical_survey_is_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr("market_farm.expectation_memory.STORE", tmp_path)
    item = make_expectation(
        event_key="LIVINGSTON:US_CPI_LEVEL:1950-06:6M",
        available_at="1950-06-30T23:59:59-04:00",
        scheduled_for="1950-12-28T23:59:59-05:00",
        indicator="US_CPI_LEVEL",
        jurisdiction="US",
        expected_value=24.0,
        unit="index",
        source="Livingston",
        source_url="https://example.test",
        visibility="quarantined_release_date_proxy",
    )
    save_expectations([item])
    rows = visible_expectations(
        datetime(1950, 6, 1, tzinfo=JST),
        datetime(1950, 7, 31, tzinfo=JST),
    )
    assert rows == []
