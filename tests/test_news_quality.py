from datetime import datetime, timezone

import pandas as pd
import pytest

from market_farm import engine, news, ledger, replay_backfill as replay
from market_farm.news_quality import historical_news_status, news_quality
from market_farm.recent_news_backtest import score_rows


ASSET = {"symbol": "TEST.T", "name": "Test", "kind": "equity", "keywords": ["Test"], "news_required_any": ["Test"]}


def test_rss_fetch_deduplicates_and_excludes_future_articles(monkeypatch):
    items = [
        {"title": "Test growth - Publisher A", "published_at": "Wed, 07 Oct 2026 10:00:00 GMT"},
        {"title": "Test growth - Publisher B", "published_at": "Wed, 07 Oct 2026 10:01:00 GMT"},
        {"title": "Test falls", "published_at": "Wed, 07 Oct 2026 14:00:00 GMT"},
    ]
    monkeypatch.setattr(news, "google_news_rss", lambda query: items)
    found, score = news.fetch_asset_news(ASSET, cutoff=datetime(2026, 10, 7, 12, tzinfo=timezone.utc))
    assert len(found) == 1
    assert score > 0


def test_relevant_article_with_unknown_time_fails_closed(monkeypatch):
    monkeypatch.setattr(news, "google_news_rss", lambda query: [{"title": "Test growth"}])
    with pytest.raises(RuntimeError, match="timestamp"):
        news.fetch_asset_news(ASSET)


def test_invalid_rss_is_failure_not_empty_news(monkeypatch):
    class Response:
        text = "<html>service unavailable</html>"
        def raise_for_status(self):
            pass
    monkeypatch.setattr(news.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError):
        news.google_news_rss("Test")


def test_quality_distinguishes_no_articles_from_failed_or_partial_collection():
    assert news_quality()["status"] == "EMPTY"
    assert news_quality()["usable"] is True
    assert news_quality(error="429")["usable"] is False
    assert news_quality(capped=1, article_count=250)["status"] == "PARTIAL"
    assert historical_news_status({"news_error": "429", "archive_articles": 0}) == "ERROR"
    assert historical_news_status({"archive_capped": True, "archive_articles": 250}) == "PARTIAL"


def test_failed_live_news_abstains_and_preserves_missing_evidence(tmp_path, monkeypatch):
    sensor = {"price": 100., "price_score": 0.8, "volatility": 0.2, "market_date": "2026-10-06"}
    monkeypatch.setattr(engine, "fetch_history", lambda *args: None)
    monkeypatch.setattr(engine, "price_sensor", lambda frame: sensor)
    monkeypatch.setattr(engine, "_load_challengers", lambda: {})
    def failed(asset):
        raise RuntimeError("HTTP 429")
    monkeypatch.setattr(engine, "fetch_asset_news", failed)
    cfg = {"assets": [ASSET], "market_proxies": {}, "timezone": "Asia/Tokyo"}
    regime, results = engine.analyze(cfg)
    result = results[0]
    assert result["news_score"] is None
    assert result["news_status"] == "ERROR"
    assert result["action"] == "NO_FORECAST"
    assert result["forecast_qualification"]["decision"] == "ABSTAIN"
    monkeypatch.setattr(ledger, "CARDS_DIR", tmp_path / "cards")
    monkeypatch.setattr(ledger, "INDEX_PATH", tmp_path / "index.json")
    card = ledger.create_live_cards(cfg, regime, results)[0]
    assert card["evidence"]["news"]["score"] is None
    assert card["evidence"]["news"]["direction"] == "UNKNOWN"
    state = engine.save_run("morning", cfg, regime, results, str(tmp_path / "state.json"))
    pred = next(iter(state["predictions"].values()))[0]
    assert pred["decision"] == "ABSTAIN"
    engine.settle_previous(state, [{"symbol": "TEST.T", "price": 110., "market_date": "2026-10-07"}])
    assert state["scores"] == {}


def test_historical_replay_records_news_failure_and_abstains(tmp_path, monkeypatch):
    cfg = {"assets": [ASSET], "market_proxies": {"sp500": "^GSPC"}}
    idx = pd.bdate_range("2025-01-01", periods=50)
    frame = pd.DataFrame({"close": 100., "price_score": .8, "macro": .1, "vol": .2,
                          "macro_status": "OK", "sp500_available_at": "2024-12-31T12:00:00+09:00"}, index=idx)
    monkeypatch.setattr(replay, "load_config", lambda: cfg)
    monkeypatch.setattr(replay, "market_frames", lambda cfg: {})
    monkeypatch.setattr(replay, "build_frame", lambda *args: frame)
    monkeypatch.setattr(replay, "REPLAY_DIR", tmp_path)
    def failed(*args):
        raise RuntimeError("HTTP 429")
    monkeypatch.setattr(replay, "fetch_gdelt_range", failed)
    out = replay.replay_month(replay.parse_month("2025-01"))
    snaps = out["assets"]["TEST.T"]["snapshots"]
    assert snaps
    assert out["replay_version"] == "replay-v2-news-availability"
    assert all(s["news_score"] is None and s["news_status"] == "ERROR" for s in snaps)
    assert all(s["forecast_qualification"]["decision"] == "ABSTAIN" for s in snaps)
    assert score_rows([{"news_direction": None, "actual_direction": "UP"}], "news_direction")["signals"] == 0


def test_company_identity_and_official_domain_are_exact():
    asset = {"news_required_any": ["KLab"], "news_trusted_sources": ["klab.com"]}
    assert news.is_relevant_item(asset, {"title": "rocklab results"})[0] is False
    assert news.is_relevant_item(asset, {"title": "Results", "source_url": "https://klab.com.evil.example/"})[0] is False
    assert news.is_relevant_item(asset, {"title": "Results", "source_url": "https://www.klab.com/"})[0] is True
