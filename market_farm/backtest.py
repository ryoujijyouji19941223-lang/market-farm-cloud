from __future__ import annotations
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .data_source import fetch_history
from .engine import load_config
from .state import load_state
from .dashboard import render


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"].astype(float)
    out = pd.DataFrame(index=close.index)
    out["close"] = close
    out["mom5"] = close / close.shift(5) - 1.0
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    out["trend"] = ma5 / ma20 - 1.0
    out["vol"] = close.pct_change().rolling(20).std() * math.sqrt(252)
    out["price_score"] = np.tanh(4.0 * out["mom5"] + 8.0 * out["trend"])
    return out


def clip(x):
    return x.clip(-1.0, 1.0)


def macro_score(asset, merged):
    risk = merged["risk_off"]
    oil = merged["oil_pressure"]
    usd = merged["usd_rate_pressure"]
    symbol = asset["symbol"]
    kind = asset["kind"]
    if symbol == "USDJPY=X":
        return 0.22 * usd + 0.10 * oil
    if symbol == "CHFJPY=X":
        return 0.16 * risk - 0.05 * usd
    if symbol == "EURJPY=X":
        return -0.05 * risk + 0.04 * oil
    if symbol == "GC=F":
        return 0.20 * risk - 0.14 * usd
    if kind == "equity":
        return -0.16 * risk
    return pd.Series(0.0, index=merged.index)


def evaluate_window(frame, start_date):
    x = frame.loc[frame.index >= start_date].dropna(subset=["prob", "actual"])
    total = int(len(x))
    signals = x[x["pred"] != "FLAT"]
    n = int(len(signals))
    correct = int((signals["pred"] == signals["actual"]).sum()) if n else 0
    return {
        "days": total,
        "signals": n,
        "correct": correct,
        "accuracy": (correct / n) if n else None,
        "signal_rate": (n / total) if total else None,
    }


def slice_accuracy(x):
    x = x.dropna(subset=["pred", "actual"])
    x = x[x["pred"] != "FLAT"]
    n = int(len(x))
    correct = int((x["pred"] == x["actual"]).sum()) if n else 0
    return {"signals": n, "correct": correct, "accuracy": (correct / n) if n else None}


def diagnostics(frame):
    x = frame.dropna(subset=["prob", "actual"]).copy()
    x["correct_flag"] = x["pred"] == x["actual"]
    x["confidence"] = (x["prob"] - 0.5).abs()
    x["factor_agree"] = (
        (np.sign(x["price_score"]) == np.sign(x["macro"])) &
        (x["price_score"].abs() >= 0.04) &
        (x["macro"].abs() >= 0.02)
    )
    signals = x[x["pred"] != "FLAT"]
    return {
        "all_signals": slice_accuracy(signals),
        "up_calls": slice_accuracy(signals[signals["pred"] == "UP"]),
        "down_calls": slice_accuracy(signals[signals["pred"] == "DOWN"]),
        "strong_calls": slice_accuracy(signals[signals["confidence"] >= 0.12]),
        "mild_calls": slice_accuracy(signals[(signals["confidence"] >= 0.05) & (signals["confidence"] < 0.12)]),
        "price_macro_agree": slice_accuracy(signals[signals["factor_agree"]]),
        "price_macro_disagree": slice_accuracy(signals[~signals["factor_agree"]]),
    }


def candidate_probability(frame, price_coef, macro_coef, edge):
    raw = price_coef * frame["price_score"] + macro_coef * frame["macro"]
    penalty = ((frame["vol"] - 0.25).clip(lower=0.0, upper=1.0)) * 0.35
    raw = raw * (1.0 - penalty)
    prob = 1.0 / (1.0 + np.exp(-2.2 * raw))
    pred = np.where(prob >= 0.5 + edge, "UP",
           np.where(prob <= 0.5 - edge, "DOWN", "FLAT"))
    return prob, pred


def score_candidate(frame, price_coef, macro_coef, edge):
    prob, pred = candidate_probability(frame, price_coef, macro_coef, edge)
    x = frame.copy()
    x["cand_prob"] = prob
    x["cand_pred"] = pred
    signals = x[x["cand_pred"] != "FLAT"].dropna(subset=["actual"])
    n = int(len(signals))
    accuracy = float((signals["cand_pred"] == signals["actual"]).mean()) if n else None
    rate = n / len(x) if len(x) else 0.0
    return {"signals": n, "accuracy": accuracy, "signal_rate": rate}


def research_candidate(frame):
    x = frame.dropna(subset=["price_score", "macro", "vol", "actual"]).copy()
    if len(x) < 150:
        return {"status": "not_enough_data"}

    cut = max(1, int(len(x) * 0.80))
    development = x.iloc[:cut]
    untouched = x.iloc[cut:]

    baseline_dev = slice_accuracy(development.assign(pred=development["pred"]))
    baseline_test = slice_accuracy(untouched.assign(pred=untouched["pred"]))

    candidates = []
    for price_coef in (-1.0, -0.5, 0.0, 0.5, 1.0):
        for macro_coef in (-1.0, -0.5, 0.0, 0.5, 1.0):
            if price_coef == 0.0 and macro_coef == 0.0:
                continue
            for edge in (0.05, 0.08, 0.12):
                dev = score_candidate(development, price_coef, macro_coef, edge)
                if dev["signals"] < max(40, int(len(development) * 0.15)):
                    continue
                candidates.append((dev["accuracy"] or 0.0, dev["signals"], price_coef, macro_coef, edge, dev))

    if not candidates:
        return {"status": "no_candidate"}

    # Pick using only the older 80%. Newest 20% is never used to choose the rule.
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    _, _, price_coef, macro_coef, edge, best_dev = candidates[0]
    best_test = score_candidate(untouched, price_coef, macro_coef, edge)

    base_acc = baseline_test.get("accuracy")
    cand_acc = best_test.get("accuracy")
    improvement = None if base_acc is None or cand_acc is None else cand_acc - base_acc
    promising = bool(
        improvement is not None and improvement >= 0.03 and
        best_test.get("signals", 0) >= 25
    )

    return {
        "status": "promising" if promising else "keep_current",
        "development_fraction": 0.80,
        "untouched_fraction": 0.20,
        "baseline_development": baseline_dev,
        "baseline_untouched": baseline_test,
        "candidate": {
            "price_coef": price_coef,
            "macro_coef": macro_coef,
            "edge": edge,
            "development": best_dev,
            "untouched": best_test,
            "untouched_improvement": improvement,
        },
        "note": "Candidate chosen on older 80%; newest 20% remained untouched until final check.",
    }


def run_backtest():
    cfg = load_config()
    period = "5y"

    proxy_features = {}
    for key, symbol in cfg["market_proxies"].items():
        try:
            proxy_features[key] = feature_frame(fetch_history(symbol, period))
        except Exception:
            proxy_features[key] = pd.DataFrame()

    assets_out = {}
    for asset in cfg["assets"]:
        try:
            df = fetch_history(asset["symbol"], period)
            feat = feature_frame(df)

            merged = feat.copy()
            for key in ("oil", "vix", "sp500", "nikkei", "us10y", "dxy"):
                pf = proxy_features.get(key)
                if pf is None or pf.empty:
                    merged[key + "_mom5"] = 0.0
                else:
                    merged[key + "_mom5"] = pf["mom5"].reindex(merged.index, method="ffill").fillna(0.0)

            merged["risk_off"] = clip(4 * merged["vix_mom5"] - 2 * merged["sp500_mom5"])
            merged["oil_pressure"] = clip(5 * merged["oil_mom5"])
            merged["japan_risk"] = clip(-3 * merged["nikkei_mom5"])
            merged["usd_rate_pressure"] = clip(4 * merged["us10y_mom5"] + 3 * merged["dxy_mom5"])
            merged["macro"] = macro_score(asset, merged)

            # Historical news is not available in this prototype.
            # Re-normalise the live price+macro weights (0.68 and 0.15) to 100%.
            combined = (0.68 / 0.83) * merged["price_score"] + (0.15 / 0.83) * merged["macro"]
            penalty = ((merged["vol"] - 0.25).clip(lower=0.0, upper=1.0)) * 0.35
            combined = combined * (1.0 - penalty)
            merged["prob"] = 1.0 / (1.0 + np.exp(-2.2 * combined))
            merged["pred"] = np.where(merged["prob"] >= 0.55, "UP",
                              np.where(merged["prob"] <= 0.45, "DOWN", "FLAT"))

            next_ret = merged["close"].shift(-1) / merged["close"] - 1.0
            merged["actual"] = np.where(next_ret > 0.002, "UP",
                                np.where(next_ret < -0.002, "DOWN", "FLAT"))
            merged.loc[next_ret.isna(), "actual"] = np.nan

            usable = merged.dropna(subset=["prob", "actual"])
            if usable.empty:
                raise RuntimeError("not enough historical data")

            end = usable.index[-1]
            windows = {
                "1y": evaluate_window(usable, end - pd.Timedelta(days=365)),
                "3y": evaluate_window(usable, end - pd.Timedelta(days=365*3)),
                "5y": evaluate_window(usable, usable.index[0]),
            }
            assets_out[asset["symbol"]] = {
                "name": asset["name"],
                "kind": asset["kind"],
                "available_start": str(usable.index[0].date()),
                "available_end": str(usable.index[-1].date()),
                "usable_days": int(len(usable)),
                "windows": windows,
                "diagnostics": diagnostics(usable),
                "research": research_candidate(usable),
            }
        except Exception as e:
            assets_out[asset["symbol"]] = {
                "name": asset["name"],
                "kind": asset["kind"],
                "error": str(e),
                "windows": {},
            }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "historical base model: price + market proxies; no historical news",
        "method": "walk-forward next-trading-day test using only data available up to each day",
        "assets": assets_out,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/backtest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    state = load_state("data/state.json")
    if state.get("runs"):
        latest = state["runs"][-1]
        render(cfg, latest["regime"], latest["results"], state)

    return out


def main():
    out = run_backtest()
    for symbol, row in out["assets"].items():
        w = row.get("windows", {}).get("5y", {})
        acc = w.get("accuracy")
        label = "-" if acc is None else f"{acc*100:.1f}%"
        print(row.get("name", symbol), "5y", label, "signals", w.get("signals", 0))


if __name__ == "__main__":
    main()
