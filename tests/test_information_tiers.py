import pytest

from market_farm.information_tiers import assert_prediction_visible
from market_farm.tealbook_research import make_tealbook_forecast, eligible_for_historical_prediction


def test_tealbook_never_becomes_historical_market_input():
    row = make_tealbook_forecast(
        research_id="gb-1975",
        forecast_made_at="1975-01-10T12:00:00-05:00",
        public_released_at="1980-01-10T12:00:00-05:00",
        indicator="US_REAL_GDP_GROWTH",
        target_period="1975-Q2",
        value=1.5,
        unit="percent",
    )
    assert eligible_for_historical_prediction(row) is False


def test_delayed_research_rejected_by_prediction_gate():
    from datetime import datetime
    row = {
        "information_tier": "delayed_research",
        "available_at": "1975-01-10T12:00:00-05:00",
    }
    with pytest.raises(ValueError):
        assert_prediction_visible(row, datetime.fromisoformat("1975-01-11T12:00:00-05:00"))
