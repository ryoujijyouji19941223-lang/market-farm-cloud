from datetime import datetime
from zoneinfo import ZoneInfo

from market_farm.actual_archive import save_rows
from market_farm.expectation_memory import make_expectation, save_expectations
from market_farm.experience_pairs import pair_index

JST = ZoneInfo("Asia/Tokyo")


def test_canonical_forecast_pairs_with_first_release(tmp_path, monkeypatch):
    exp_store = tmp_path / "expectations"
    actual_store = tmp_path / "actuals"
    monkeypatch.setattr("market_farm.expectation_memory.STORE", exp_store)
    monkeypatch.setattr("market_farm.actual_archive.STORE", actual_store)

    exp = make_expectation(
        event_key="US_REAL_GDP:2026-Q2",
        available_at="2026-05-20T23:59:59-04:00",
        scheduled_for="2026-07-31T23:59:59-04:00",
        indicator="US_REAL_GDP_GROWTH",
        jurisdiction="US",
        expected_value=2.1,
        unit="percent",
        source="SPF",
        source_url="https://example.test/spf",
        visibility="public",
        observation_basis="professional_forecaster_survey",
        target_period="2026-Q2",
    )
    save_expectations([exp])

    save_rows("test", [{
        "record_id": "RTDSM:US_REAL_GDP_GROWTH:2026-Q2:r1",
        "event_key": "US_REAL_GDP:2026-Q2",
        "indicator": "US_REAL_GDP_GROWTH",
        "value": 2.8,
        "unit": "percent",
        "available_at": "2026-07-31T23:59:59-04:00",
        "observation_period": "2026-Q2",
        "vintage": "release_1",
        "source": "Philadelphia Fed RTDS",
        "source_url": "https://example.test/rtds",
        "information_tier": "public_realtime",
        "release_number": 1,
    }])

    pairs = pair_index()
    assert len(pairs) == 1
    assert pairs[0]["event_key"] == "US_REAL_GDP:2026-Q2"
    assert pairs[0]["expectation_source"] == "SPF"
