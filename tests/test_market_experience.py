from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_farm.actual_release import make_actual, validate_pair
from market_farm.market_experience import make_experience
from market_farm.reaction_memory import reaction_from_frame

JST = ZoneInfo("Asia/Tokyo")


def test_expectation_must_precede_actual():
    actual = make_actual(
        record_id="a1", event_key="CPI:2026-08", indicator="US_CPI_YOY",
        value=2.9, unit="percent", available_at="2026-09-11T21:30:00+09:00",
        observation_period="2026-08", vintage="first_release",
        source="BLS", source_url="https://example.test",
    )
    expectation = {
        "event_key": "CPI:2026-08", "available_at": "2026-09-11T22:00:00+09:00",
        "unit": "percent",
    }
    with pytest.raises(ValueError):
        validate_pair(expectation, actual)


def test_reaction_is_measured_after_release():
    idx = pd.date_range("2026-09-11", periods=8, freq="D", tz=JST)
    frame = pd.DataFrame({"close": [100, 101, 102, 103, 104, 105, 106, 107]}, index=idx)
    out = reaction_from_frame(frame, "2026-09-11T21:30:00+09:00")
    assert out["status"] == "OK"
    assert out["base_time"].startswith("2026-09-12")
    assert out["horizons"]["1d"]["return"] > 0


def test_experience_rejects_future_actual():
    with pytest.raises(ValueError):
        make_experience(
            event_key="x", information_cutoff="2026-09-11T20:00:00+09:00",
            expectation=None,
            actual={"record_id": "a", "available_at": "2026-09-11T21:30:00+09:00", "value": 1},
            surprise={}, semantic={}, reactions={}, provenance={},
        )
