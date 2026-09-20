from datetime import datetime
from zoneinfo import ZoneInfo

from market_farm import ledger


def sample_result(market_date="2026-09-21", price=100.0):
    return {
        "symbol": "TEST",
        "name": "テスト",
        "kind": "equity",
        "price": price,
        "market_date": market_date,
        "day_change": 0.01,
        "momentum5": 0.02,
        "trend": 0.01,
        "volatility": 0.20,
        "price_score": 0.15,
        "news_score": 0.10,
        "macro_score": 0.05,
        "probability_up": 0.60,
        "challenger": None,
        "news": [{"title": "good news", "link": "https://example.com"}],
    }


def test_prediction_card_freezes_and_settles_only_on_new_market_date(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "CARDS_DIR", tmp_path / "cards")
    monkeypatch.setattr(ledger, "INDEX_PATH", tmp_path / "cards_index.json")

    cfg = {"timezone": "Asia/Tokyo", "model_version": "test-v1"}
    regime = {"risk_off": 0.0, "oil_pressure": 0.0, "japan_risk": 0.0, "usd_rate_pressure": 0.0}
    now = datetime(2026, 9, 21, 8, 7, tzinfo=ZoneInfo("Asia/Tokyo"))

    cards = ledger.create_live_cards(cfg, regime, [sample_result()], now=now)
    assert len(cards) == 1
    assert cards[0]["status"] == "OPEN"
    assert cards[0]["model_version"] == "test-v1"
    assert cards[0]["evidence"]["news"]["headlines"][0]["title"] == "good news"

    # Same market date must not be treated as a new outcome.
    settled = ledger.settle_live_cards([sample_result(market_date="2026-09-21", price=101.0)])
    assert settled == []

    # A genuinely later market date can settle the card.
    settled = ledger.settle_live_cards([sample_result(market_date="2026-09-22", price=101.0)])
    assert len(settled) == 1
    assert settled[0]["status"] == "SETTLED"
    assert settled[0]["outcome"]["direction"] == "UP"
    assert settled[0]["outcome"]["correct"] is True
    assert settled[0]["review"]["result_type"] == "一致"


def test_prediction_card_is_not_overwritten_by_same_day_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "CARDS_DIR", tmp_path / "cards")
    monkeypatch.setattr(ledger, "INDEX_PATH", tmp_path / "cards_index.json")

    cfg = {"timezone": "Asia/Tokyo", "model_version": "test-v1"}
    regime = {"risk_off": 0.0, "oil_pressure": 0.0, "japan_risk": 0.0, "usd_rate_pressure": 0.0}
    first = datetime(2026, 9, 21, 8, 7, tzinfo=ZoneInfo("Asia/Tokyo"))
    later = datetime(2026, 9, 21, 11, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

    first_cards = ledger.create_live_cards(cfg, regime, [sample_result(price=100.0)], now=first)
    rerun_cards = ledger.create_live_cards(cfg, regime, [sample_result(price=110.0)], now=later)

    assert first_cards[0]["reference_price"] == 100.0
    assert rerun_cards[0]["reference_price"] == 100.0

    saved = ledger._load_json(ledger._card_path("2026-09-21", "TEST"), {})
    assert saved["reference_price"] == 100.0
    assert saved["created_at_jst"] == first.isoformat()
