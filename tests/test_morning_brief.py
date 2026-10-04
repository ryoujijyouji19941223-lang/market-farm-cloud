from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market_farm import morning_brief as module


JST = ZoneInfo("Asia/Tokyo")


def _result(symbol, name, market_date, prob, decision, action, price=100.0):
    return {
        "symbol": symbol,
        "name": name,
        "kind": "equity",
        "price": price,
        "market_date": market_date,
        "day_change": 0.01,
        "probability_up": prob,
        "action": action,
        "forecast_qualification": {
            "direction": "UP" if prob >= .55 else ("DOWN" if prob <= .45 else "FLAT"),
            "decision": decision,
            "evidence_strength": 0.2,
            "factor_agreement": 0.66,
            "reason": None if decision == "FORECAST" else "insufficient_evidence",
        },
        "price_score": 0.1,
        "news_score": 0.0,
        "macro_score": 0.0,
    }


def test_brief_keeps_generation_date_separate_from_market_date(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "CARDS_INDEX_PATH", tmp_path / "cards_index.json")
    monkeypatch.setattr(module, "RESEARCH_PATH", tmp_path / "research.json")

    state = {
        "runs": [{
            "timestamp": "2026-10-03T01:36:00+09:00",
            "session": "evening",
            "results": [{
                "symbol": "AAA",
                "market_date": "2026-10-01",
            }],
        }]
    }
    results = [
        _result("AAA", "A", "2026-10-02", .70, "FORECAST", "UP"),
        _result("BBB", "B", "2026-10-01", .52, "ABSTAIN", "NO_FORECAST"),
    ]
    out = tmp_path / "morning_brief.json"

    payload = module.build_morning_brief(
        {"timezone": "Asia/Tokyo"},
        {"risk_off": 0.0},
        results,
        state=state,
        session="newspaper",
        now=datetime(2026, 10, 4, 8, 25, tzinfo=JST),
        out=out,
    )

    assert payload["date_semantics"]["brief_date"] == "2026-10-04"
    assert payload["date_semantics"]["market_dates"]["dates_present"] == [
        "2026-10-01", "2026-10-02"
    ]
    assert payload["snapshot_consistency"]["status"] == "MIXED_TIMESTAMPS"
    assert payload["current_analysis"]["forecast_count"] == 1
    assert payload["current_analysis"]["abstain_count"] == 1
    assert payload["consumer_contract"]["primary_source"] == "data/morning_brief.json"
    assert payload["snapshot_id"]
    assert out.exists()


def test_answer_check_waits_for_latest_open_forecast(tmp_path, monkeypatch):
    card_dir = tmp_path / "cards"
    card_dir.mkdir()
    card_path = card_dir / "AAA.json"
    card_path.write_text(
        """{
          "prediction_date":"2026-10-02",
          "name":"A",
          "symbol":"AAA",
          "market_data_through":"2026-10-02",
          "reference_price":100,
          "prediction":{
            "direction":"DOWN",
            "direction_score":0.31,
            "qualification":{"decision":"FORECAST"}
          },
          "outcome":null,
          "review":null
        }""",
        encoding="utf-8",
    )
    cards_index = tmp_path / "cards_index.json"
    cards_index.write_text(
        """{
          "updated_at":"2026-10-03T00:00:00+00:00",
          "recent":[{
            "prediction_date":"2026-10-02",
            "symbol":"AAA",
            "name":"A",
            "status":"OPEN",
            "direction":"DOWN",
            "score":0.31,
            "decision":"FORECAST",
            "market_data_through":"2026-10-02",
            "path":"CARD_PATH"
          }]
        }""".replace("CARD_PATH", str(card_path).replace("\\", "\\\\")),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "CARDS_INDEX_PATH", cards_index)

    answer = module._answer_check(module._load_json(cards_index, {}))
    assert answer["status"] == "WAITING"
    assert answer["headline"] == "まだ答え待ち"
    assert answer["card"]["asset"] == "A"
    assert answer["card"]["direction_meter"] == 31


def test_answer_check_returns_one_settled_forecast(tmp_path):
    card_path = tmp_path / "AAA.json"
    card_path.write_text(
        """{
          "prediction_date":"2026-10-01",
          "name":"A",
          "symbol":"AAA",
          "market_data_through":"2026-10-01",
          "reference_price":100,
          "prediction":{
            "direction":"DOWN",
            "direction_score":0.30,
            "qualification":{"decision":"FORECAST"}
          },
          "outcome":{
            "market_date":"2026-10-02",
            "price":98,
            "change":-0.02,
            "direction":"DOWN",
            "correct":true
          },
          "review":{"result_type":"一致"}
        }""",
        encoding="utf-8",
    )
    cards_index = {
        "recent": [{
            "prediction_date": "2026-10-01",
            "symbol": "AAA",
            "name": "A",
            "status": "SETTLED",
            "direction": "DOWN",
            "score": 0.30,
            "decision": "FORECAST",
            "market_data_through": "2026-10-01",
            "correct": True,
            "result_type": "一致",
            "path": str(card_path),
        }]
    }

    answer = module._answer_check(cards_index)
    assert answer["status"] == "READY"
    assert answer["card"]["actual_direction"] == "DOWN"
    assert answer["card"]["correct"] is True
    assert answer["learning"] is not None
