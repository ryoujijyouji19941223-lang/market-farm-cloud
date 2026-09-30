from datetime import datetime
from zoneinfo import ZoneInfo

from market_farm.event_memory import group_evidence
from market_farm.official_archive import make_record, visible_official


JST = ZoneInfo("Asia/Tokyo")


def test_official_record_requires_timezone():
    try:
        make_record(
            available_at="2026-06-01T10:00:00",
            authority="test", source_type="policy", jurisdiction="JP",
            title="x", url="https://example.test/x",
        )
        assert False
    except ValueError:
        pass


def test_later_official_release_hidden():
    cutoff = datetime(2026, 6, 1, 12, 0, tzinfo=JST)
    rows = [
        {"available_at": "2026-06-01T10:00:00+09:00", "title": "known"},
        {"available_at": "2026-06-01T13:00:00+09:00", "title": "future"},
    ]
    assert [x["title"] for x in visible_official(rows, cutoff)] == ["known"]


def test_event_grouping_does_not_invent_causality():
    rows = [
        {"evidence_id": "a", "available_at": "2026-06-01T10:00:00+09:00", "entities": ["BOJ"], "tags": ["rates"], "reliability": "primary"},
        {"evidence_id": "b", "available_at": "2026-06-01T11:00:00+09:00", "entities": ["BOJ"], "tags": ["rates"], "reliability": "secondary"},
    ]
    events = group_evidence(rows)
    assert len(events) == 1
    assert events[0]["evidence_count"] == 2
    assert events[0]["primary_evidence_count"] == 1
    assert events[0]["causal_claim"] is None
