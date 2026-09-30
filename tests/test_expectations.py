from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_farm.expectation_memory import make_expectation
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
