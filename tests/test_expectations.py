from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_farm.expectation_memory import make_expectation, save_expectations, visible_expectations
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
