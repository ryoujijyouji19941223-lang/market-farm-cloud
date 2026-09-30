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
