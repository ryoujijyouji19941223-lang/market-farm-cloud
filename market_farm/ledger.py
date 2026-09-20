from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .data_source import fetch_history

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
    # results tells us which symbols are still active/available. The actual
    # outcome is taken from daily history so a missed GitHub run cannot turn
    # a next-trading-day forecast into a two-days-later forecast.
    active_symbols = {
        r["symbol"] for r in results
        if r.get("price") is not None
    }
    settled = []
    history_cache = {}

    if not CARDS_DIR.exists():
        return settled

    for path in sorted(CARDS_DIR.glob("*/*.json")):
        card = _load_json(path, {})
        if not card or card.get("status") != "OPEN":
            continue

        symbol = card.get("symbol")
        if symbol not in active_symbols:
            continue

        ref_market_date = card.get("market_data_through")
        ref_price = card.get("reference_price")
        if not ref_market_date or not ref_price:
            continue

        try:
            if symbol not in history_cache:
                history_cache[symbol] = fetch_history(symbol, "3mo")
            df = history_cache[symbol]
        except Exception:
            # Safer to leave a card open than to score it with the wrong day.
            continue

        ref_day = datetime.fromisoformat(str(ref_market_date)).date()
        candidates = []
        for idx in df.index:
            try:
                day = idx.date()
            except Exception:
                day = datetime.fromisoformat(str(idx)).date()
            if day > ref_day:
                candidates.append((day, idx))

        if not candidates:
            continue

        # The first actually traded market date after the frozen reference.
        target_day, target_idx = min(candidates, key=lambda x: x[0])
        try:
            target_price = float(df.loc[target_idx, "Close"])
        except Exception:
            continue

        change = target_price / float(ref_price) - 1.0
        actual = "UP" if change > 0.002 else ("DOWN" if change < -0.002 else "FLAT")
        correct = actual == card.get("prediction", {}).get("direction")

        card["status"] = "SETTLED"
        card["outcome"] = {
            "market_date": target_day.isoformat(),
            "price": target_price,
            "change": change,
            "direction": actual,
            "correct": bool(correct),
            "settled_at_jst": (now or datetime.now().astimezone()).isoformat(),
            "target_policy": "FIRST_TRADED_MARKET_DATE_AFTER_REFERENCE",
            "price_source": "yfinance daily adjusted close",
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
