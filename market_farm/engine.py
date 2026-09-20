from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path
from .data_source import fetch_history
from .sensors import price_sensor, market_regime, regime_adjustment, risk_adjust, probability
from .news import fetch_asset_news
from .state import load_state, save_state


def load_config(path="config.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_challengers(path="data/backtest.json"):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for symbol, row in data.get("assets", {}).items():
        research = row.get("research", {})
        candidate = research.get("candidate", {})
        if research.get("status") != "promising":
            continue
        out[symbol] = {
            "price_coef": candidate.get("price_coef"),
            "macro_coef": candidate.get("macro_coef"),
            "edge": candidate.get("edge"),
            "heldout_accuracy": candidate.get("untouched", {}).get("accuracy"),
            "heldout_signals": candidate.get("untouched", {}).get("signals"),
        }
    return out


def _challenger_signal(symbol, p, macro, challengers):
    ch = challengers.get(symbol)
    if not ch:
        return None
    raw = ch["price_coef"] * p["price_score"] + ch["macro_coef"] * macro
    raw = risk_adjust(raw, p["volatility"])
    prob = probability(raw)
    edge = ch["edge"]
    direction = "UP" if prob >= 0.5 + edge else ("DOWN" if prob <= 0.5 - edge else "FLAT")
    return {
        "probability_up": prob,
        "direction": direction,
        **ch,
    }


def analyze(cfg):
    challengers = _load_challengers()
    proxies = {}
    for key, sym in cfg["market_proxies"].items():
        try:
            proxies[key] = price_sensor(fetch_history(sym))
        except Exception:
            proxies[key] = {}
    regime = market_regime(proxies)

    results = []
    for asset in cfg["assets"]:
        try:
            p = price_sensor(fetch_history(asset["symbol"]))
            try:
                news, nscore = fetch_asset_news(asset)
            except Exception:
                news, nscore = [], 0.0
            macro = regime_adjustment(asset["symbol"], asset["kind"], regime)
            combined = 0.68*p["price_score"] + 0.17*nscore + 0.15*macro
            combined = risk_adjust(combined, p["volatility"])
            prob = probability(combined)
            if prob >= cfg["buy_threshold"]:
                action = "BUY_CANDIDATE"
            elif prob <= cfg["sell_threshold"]:
                action = "RISK_OFF"
            else:
                action = "HOLD"
            challenger = _challenger_signal(asset["symbol"], p, macro, challengers)
            results.append({**asset, **p, "news_score": nscore, "macro_score": macro, "score": combined,
                            "probability_up": prob, "action": action, "news": news[:5],
                            "challenger": challenger})
        except Exception as e:
            results.append({**asset, "error": str(e), "probability_up": 0.5, "action":"NO_DATA"})
    return regime, results


def _settle_prediction_bucket(state, results, prediction_key, score_key):
    current = {
        r["symbol"]: {"price": r.get("price"), "market_date": r.get("market_date")}
        for r in results if r.get("price") is not None
    }
    for day, preds in list(state.get(prediction_key, {}).items()):
        for pred in preds:
            if pred.get("settled") or pred["symbol"] not in current:
                continue
            ref = pred.get("reference_price")
            now_info = current[pred["symbol"]]
            now = now_info["price"]
            ref_market_date = pred.get("reference_market_date")
            now_market_date = now_info.get("market_date")
            # Do not score a holiday/weekend refresh as a new market outcome.
            if ref_market_date and now_market_date and now_market_date <= ref_market_date:
                continue
            if not ref:
                continue
            change = now/ref - 1
            actual = "UP" if change > 0.002 else ("DOWN" if change < -0.002 else "FLAT")
            pred["actual_direction"] = actual
            pred["actual_price"] = now
            pred["correct"] = actual == pred["direction"]
            pred["settled"] = True
            s = state[score_key].setdefault(pred["symbol"], {"correct":0, "total":0})
            s["total"] += 1
            s["correct"] += int(pred["correct"])


def settle_previous(state, results):
    _settle_prediction_bucket(state, results, "predictions", "scores")
    _settle_prediction_bucket(state, results, "challenger_predictions", "challenger_scores")


def save_run(session, cfg, regime, results, state_path="data/state.json"):
    state = load_state(state_path)
    settle_previous(state, results)
    tz = ZoneInfo(cfg["timezone"])
    now = datetime.now(tz)
    run = {"timestamp": now.isoformat(), "session": session, "regime": regime,
           "results": [{k:v for k,v in r.items() if k != "news"} for r in results]}
    state["runs"].append(run)
    state["runs"] = state["runs"][-120:]
    if session == "morning":
        key = now.date().isoformat()
        state["predictions"][key] = []
        state["challenger_predictions"][key] = []
        for r in results:
            if r.get("price") is None:
                continue
            p = r["probability_up"]
            direction = "UP" if p >= .55 else ("DOWN" if p <= .45 else "FLAT")
            state["predictions"][key].append({"symbol": r["symbol"], "name":r["name"], "direction":direction,
                                               "probability_up":p, "reference_price":r["price"],
                                               "reference_market_date": r.get("market_date"),
                                               "settled":False})
            ch = r.get("challenger")
            if ch:
                state["challenger_predictions"][key].append({
                    "symbol": r["symbol"], "name": r["name"],
                    "direction": ch["direction"],
                    "probability_up": ch["probability_up"],
                    "reference_price": r["price"],
                    "reference_market_date": r.get("market_date"),
                    "settled": False
                })
    save_state(state, state_path)
    return state
