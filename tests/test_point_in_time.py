from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_farm.point_in_time import (
    FutureInformationLeak,
    PointInTimeRecord,
    assert_market_frame_cutoff,
    assert_snapshot_metadata,
    visible_records,
)


JST = ZoneInfo("Asia/Tokyo")


def test_market_frame_rejects_future_row():
    frame = pd.DataFrame({"close": [100, 101]}, index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    with pytest.raises(FutureInformationLeak):
        assert_market_frame_cutoff(frame, date(2020, 1, 2))


def test_market_frame_accepts_rows_through_cutoff():
    frame = pd.DataFrame({"close": [99, 100]}, index=pd.to_datetime(["2020-01-01", "2020-01-02"]))
    assert_market_frame_cutoff(frame, date(2020, 1, 2))


def test_point_in_time_records_hide_later_release():
    cutoff = datetime(2020, 1, 2, 23, 59, tzinfo=JST)
    records = [
        PointInTimeRecord(1.0, date(2019, 12, 1), datetime(2020, 1, 2, 8, 30, tzinfo=JST)),
        PointInTimeRecord(2.0, date(2019, 12, 1), datetime(2020, 1, 3, 8, 30, tzinfo=JST)),
    ]
    assert [r.value for r in visible_records(records, cutoff)] == [1.0]


def test_snapshot_rejects_price_date_after_cutoff():
    snapshot = {
        "information_cutoff_jst": "2020-01-02T23:59:59+09:00",
        "price_data_through": "2020-01-03",
    }
    with pytest.raises(FutureInformationLeak):
        assert_snapshot_metadata(snapshot)


def test_news_guard_accepts_replay_seen_jst_and_rejects_future():
    from market_farm.point_in_time import assert_articles_cutoff

    cutoff = datetime(2020, 1, 2, 23, 59, tzinfo=JST)
    safe = [{"title": "known", "seen_jst": "2020-01-02T20:00:00+09:00"}]
    assert_articles_cutoff(safe, cutoff)

    future = [{"title": "future", "seen_jst": "2020-01-03T00:01:00+09:00"}]
    with pytest.raises(FutureInformationLeak):
        assert_articles_cutoff(future, cutoff)


def test_snapshot_accepts_point_in_time_metadata():
    snapshot = {
        "information_cutoff_jst": "2020-01-02T23:59:59+09:00",
        "price_data_through": "2020-01-02",
    }
    assert_snapshot_metadata(snapshot)


def test_us_same_date_proxy_is_not_visible_at_japan_end_of_day():
    from market_farm.point_in_time import align_daily_proxy, daily_available_at
    frame = pd.DataFrame({"mom5": [.1, .9]}, index=pd.to_datetime(["2020-01-01", "2020-01-02"]))
    cutoff = datetime(2020, 1, 2, 23, 59, tzinfo=JST)
    values, stamps = align_daily_proxy(frame, "^GSPC", [cutoff], pd.to_datetime(["2020-01-02"]))
    assert values.iloc[0] == .1
    assert datetime.fromisoformat(stamps[0]) <= cutoff
    assert daily_available_at("2020-01-02", "^GSPC") > cutoff


@pytest.mark.parametrize("extra", [
    {"proxy_available_at": {"sp500": "2020-01-03T12:00:00+09:00"}},
    {"horizons": {"next_day": {"available_at": "2020-01-02T18:00:00+09:00"}}},
])
def test_snapshot_rejects_future_feature_and_already_known_outcome(extra):
    with pytest.raises(FutureInformationLeak):
        assert_snapshot_metadata({"information_cutoff_jst": "2020-01-02T23:59:59+09:00", "price_data_through": "2020-01-02", **extra})


def test_reaction_session_date_is_resolved_to_close_including_dst():
    from market_farm.point_in_time import reaction_available_at
    reaction = {"market_timezone": "America/New_York", "market_close": "16:00",
                "horizons": {"1d": {"time": "2020-07-01T00:00:00"}}}
    stamp = reaction_available_at(reaction, "1d")
    assert stamp.isoformat() == "2020-07-01T16:00:00-04:00"
