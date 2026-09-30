from datetime import datetime
from zoneinfo import ZoneInfo

from market_farm.world_memory import world_as_of
from market_farm.news_archive import ARCHIVE


def test_world_memory_never_returns_future_news(tmp_path, monkeypatch):
    monkeypatch.setattr("market_farm.news_archive.ARCHIVE", tmp_path)
    monkeypatch.setattr("market_farm.world_memory.load_range", lambda start, end: [
        {
            "id": "safe",
            "title": "Known now",
            "url": "https://example.test/a",
            "domain": "example.test",
            "seen_jst": "2026-06-01T12:00:00+09:00",
            "provider": "test",
            "query": "economy",
            "_seen": datetime.fromisoformat("2026-06-01T12:00:00+09:00"),
        }
    ])
    cutoff = datetime(2026, 6, 1, 23, 59, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    snap = world_as_of(cutoff)
    assert snap["evidence_count"] == 1
    assert snap["evidence"][0]["title"] == "Known now"


def test_world_memory_source_mix(monkeypatch):
    monkeypatch.setattr("market_farm.world_memory.load_range", lambda start, end: [
        {
            "id": "boj",
            "title": "Policy statement",
            "url": "https://www.boj.or.jp/x",
            "domain": "boj.or.jp",
            "seen_jst": "2026-06-01T10:00:00+09:00",
            "provider": "official",
            "query": "rates",
            "_seen": datetime.fromisoformat("2026-06-01T10:00:00+09:00"),
        },
        {
            "id": "news",
            "title": "Market report",
            "url": "https://example.test/b",
            "domain": "example.test",
            "seen_jst": "2026-06-01T11:00:00+09:00",
            "provider": "news",
            "query": "rates",
            "_seen": datetime.fromisoformat("2026-06-01T11:00:00+09:00"),
        },
    ])
    cutoff = datetime(2026, 6, 1, 23, 59, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    snap = world_as_of(cutoff)
    assert snap["source_mix"]["primary"] == 1
    assert snap["source_mix"]["secondary"] == 1
