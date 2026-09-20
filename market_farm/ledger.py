from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CARDS_DIR = Path("data/cards")
INDEX_PATH = Path("data/cards_index.json")


def _safe_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", symbol)


def _direction(prob: float) -> str:
    if prob >= 0.55:
        return "UP"
    if prob <= 0.45:
        return "DOWN"
    return "FLAT"


def _factor_direction(value: float, threshold: float = 0.04) -> str:
    if value >= threshold:
        return "UP"
    if value <= -threshold:
        return "DOWN"
    return "NEUTRAL"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _card_path(date_key: str, symbol: str) -> Path:
    return CARDS_DIR / date_key / f"{_safe_symbol(symbol)}.json"


def _news_evidence(result: dict):
    items = []
    for item in result.get("news", [])[:5]:
        items.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
        })
    return items


def create_live_cards(cfg: dict, regime: dict, results: list[dict], now: datetime | None = None):
    tz = ZoneInfo(cfg.get("timezone", "Asia/Tokyo"))
    now = now or datetime.now(tz)
    date_key = now.date().isoformat()
    model_version = cfg.get("model_version", "live-v0.4")

    created = []
    for r in results:
        if r.get("price") is None:
            continue

        prob = float(r.get("probability_up", 0.5))
        direction = _direction(prob)
        factors = {
            "price": {
                "score": float(r.get("price_score", 0.0)),
                "direction": _factor_direction(float(r.get("price_score", 0.0))),
                "day_change": float(r.get("day_change", 0.0)),
                "momentum5": float(r.get("momentum5", 0.0)),
                "trend": float(r.get("trend", 0.0)),
                "volatility": float(r.get("volatility", 0.0)),
            },
            "news": {
                "score": float(r.get("news_score", 0.0)),
                "direction": _factor_direction(float(r.get("news_score", 0.0))),
                "headlines": _news_evidence(r),
            },
            "outside_wind": {
                "score": float(r.get("macro_score", 0.0)),
                "direction": _factor_direction(float(r.get("macro_score", 0.0))),
                "regime_snapshot": {k: float(v) for k, v in regime.items()},
            },
        }

        path = _card_path(date_key, r["symbol"])
        # The first morning card is the historical record. A delayed/manual
        # rerun on the same day must never rewrite it with later information.
        if path.exists():
            created.append(_load_json(path, {}))
            continue

        card = {
            "schema_version": 1,
            "model_version": model_version,
            "status": "OPEN",
            "created_at_jst": now.isoformat(),
            "prediction_date": date_key,
            "symbol": r["symbol"],
            "name": r["name"],
            "kind": r["kind"],
            "horizon": "NEXT_TRADING_DAY",
            "information_cutoff_jst": now.isoformat(),
            "market_data_through": r.get("market_date"),
            "reference_price": float(r["price"]),
            "prediction": {
                "direction": direction,
                "direction_score": prob,
                "note": "direction_score is a model score, not a calibrated probability",
            },
            "challenger": r.get("challenger"),
            "evidence": factors,
            "sources": {
                "price": "yfinance daily market data",
                "live_news": "Google News RSS headlines",
                "outside_wind": "market proxies: VIX, S&P500, US10Y, DXY, oil, Nikkei",
            },
            "outcome": None,
            "review": None,
        }
        _save_json(path, card)
        created.append(card)

    _refresh_index()
    return created


def _review(card: dict, actual: str, change: float):
    pred = card.get("prediction", {}).get("direction")
    evidence = card.get("evidence", {})
    factor_dirs = {
        key: value.get("direction")
        for key, value in evidence.items()
        if isinstance(value, dict) and "direction" in value
    }

    if pred == actual:
        result_type = "一致"
    elif pred == "FLAT" and actual != "FLAT":
        result_type = "動きを見逃した"
    elif pred != "FLAT" and actual == "FLAT":
        result_type = "動くと読んだが横ばい"
    else:
        result_type = "方向を逆に読んだ"

    supporting = [k for k, d in factor_dirs.items() if d == pred]
    opposing = [k for k, d in factor_dirs.items() if d not in (pred, "NEUTRAL")]
    neutral = [k for k, d in factor_dirs.items() if d == "NEUTRAL"]

    return {
        "result_type": result_type,
        "supporting_factors": supporting,
        "opposing_factors": opposing,
        "neutral_factors": neutral,
        "factor_directions": factor_dirs,
        "actual_change": change,
        "note": "This is a mechanical post-mortem classification, not a causal proof.",
    }


def settle_live_cards(results: list[dict], now: datetime | None = None):
    current = {
        r["symbol"]: r
        for r in results
        if r.get("price") is not None
    }
    settled = []

    if not CARDS_DIR.exists():
        return settled

    for path in sorted(CARDS_DIR.glob("*/*.json")):
        card = _load_json(path, {})
        if not card or card.get("status") != "OPEN":
            continue
        r = current.get(card.get("symbol"))
        if not r:
            continue

        old_market_date = card.get("market_data_through")
        new_market_date = r.get("market_date")
        if old_market_date and new_market_date and new_market_date <= old_market_date:
            continue

        ref = card.get("reference_price")
        now_price = r.get("price")
        if not ref or now_price is None:
            continue

        change = float(now_price) / float(ref) - 1.0
        actual = "UP" if change > 0.002 else ("DOWN" if change < -0.002 else "FLAT")
        correct = actual == card.get("prediction", {}).get("direction")

        card["status"] = "SETTLED"
        card["outcome"] = {
            "market_date": new_market_date,
            "price": float(now_price),
            "change": change,
            "direction": actual,
            "correct": bool(correct),
            "settled_at_jst": (now or datetime.now().astimezone()).isoformat(),
        }
        card["review"] = _review(card, actual, change)
        _save_json(path, card)
        settled.append(card)

    _refresh_index()
    return settled


def _refresh_index():
    rows = []
    if CARDS_DIR.exists():
        for path in sorted(CARDS_DIR.glob("*/*.json"), reverse=True):
            card = _load_json(path, {})
            if not card:
                continue
            rows.append({
                "prediction_date": card.get("prediction_date"),
                "symbol": card.get("symbol"),
                "name": card.get("name"),
                "status": card.get("status"),
                "direction": card.get("prediction", {}).get("direction"),
                "score": card.get("prediction", {}).get("direction_score"),
                "market_data_through": card.get("market_data_through"),
                "correct": (card.get("outcome") or {}).get("correct"),
                "result_type": (card.get("review") or {}).get("result_type"),
                "path": str(path),
            })

    settled = [r for r in rows if r.get("status") == "SETTLED"]
    correct = sum(1 for r in settled if r.get("correct"))
    index = {
        "updated_at": datetime.now().astimezone().isoformat(),
        "cards_total": len(rows),
        "cards_open": sum(1 for r in rows if r.get("status") == "OPEN"),
        "cards_settled": len(settled),
        "cards_correct": correct,
        "accuracy": (correct / len(settled)) if settled else None,
        "recent": rows[:36],
    }
    _save_json(INDEX_PATH, index)
