from __future__ import annotations

import json
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .backtest import feature_frame, clip, macro_score
from .data_source import fetch_history
from .engine import load_config
from .news import sentiment
from .recent_news_backtest import fetch_gdelt_range, window_articles, article_public
from .sensors import risk_adjust, probability
from .state import load_state
from .dashboard import render
from .research_report import build_report

JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")

PROGRESS = Path("data/replay_progress.json")
REPLAY_DIR = Path("data/replay")


def month_start(dt):
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def previous_month(dt):
    first = month_start(dt)
    return month_start(first - timedelta(days=1))


def month_end(dt):
    return previous_month(month_start(dt) + timedelta(days=32)) + timedelta(days=32)


def add_month(dt):
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1, day=1)
    return dt.replace(month=dt.month + 1, day=1)


def load_progress():
    if PROGRESS.exists():
        try:
            return json.loads(PROGRESS.read_text(encoding="utf-8"))
        except Exception:
            pass
    now = datetime.now(JST)
    first = previous_month(now)
    oldest = month_start(now - timedelta(days=365 * 5))
    return {
        "next_month": first.strftime("%Y-%m"),
        "oldest_month": oldest.strftime("%Y-%m"),
        "completed_months": [],
        "failed_months": [],
    }


def save_progress(progress):
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_month(value):
    return datetime.strptime(value + "-01", "%Y-%m-%d").replace(tzinfo=JST)


def market_frames(cfg):
    proxies = {}
    for key, symbol in cfg["market_proxies"].items():
        try:
            proxies[key] = feature_frame(fetch_history(symbol, "10y"))
        except Exception:
            proxies[key] = pd.DataFrame()
    return proxies


def build_frame(asset, proxies):
    df = fetch_history(asset["symbol"], "10y")
    feat = feature_frame(df)
    merged = feat.copy()

    close = df["Close"].astype(float)
    merged["mom20"] = close / close.shift(20) - 1.0
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    merged["trend60"] = ma20 / ma60 - 1.0

    for key in ("oil", "vix", "sp500", "nikkei", "us10y", "dxy"):
        pf = proxies.get(key)
        if pf is None or pf.empty:
            merged[key + "_mom5"] = 0.0
        else:
            merged[key + "_mom5"] = pf["mom5"].reindex(merged.index, method="ffill").fillna(0.0)

    merged["risk_off"] = clip(4 * merged["vix_mom5"] - 2 * merged["sp500_mom5"])
    merged["oil_pressure"] = clip(5 * merged["oil_mom5"])
    merged["japan_risk"] = clip(-3 * merged["nikkei_mom5"])
    merged["usd_rate_pressure"] = clip(4 * merged["us10y_mom5"] + 3 * merged["dxy_mom5"])
    merged["macro"] = macro_score(asset, merged)
    return merged


def direction(prob, edge=0.05):
    if prob >= 0.5 + edge:
        return "UP"
    if prob <= 0.5 - edge:
        return "DOWN"
    return "FLAT"


def actual_direction(change, flat_band):
    if change > flat_band:
        return "UP"
    if change < -flat_band:
        return "DOWN"
    return "FLAT"


def score_snapshot(price_score, macro, news_score, vol):
    raw = 0.68 * price_score + 0.17 * news_score + 0.15 * macro
    raw = risk_adjust(raw, vol)
    prob = probability(raw)
    return float(prob), direction(prob)


def cutoff_for(anchor_date):
    return datetime.combine(anchor_date, dtime(23, 59, 59), tzinfo=JST)


def future_result(frame, pos, steps, flat_band):
    target = pos + steps
    if target >= len(frame.index):
        return None
    anchor_close = float(frame.iloc[pos]["close"])
    target_close = float(frame.iloc[target]["close"])
    change = target_close / anchor_close - 1.0
    return {
        "target_date": pd.Timestamp(frame.index[target]).date().isoformat(),
        "change": float(change),
        "direction": actual_direction(change, flat_band),
        "target_close": target_close,
    }


def replay_month(month_dt):
    cfg = load_config()
    proxies = market_frames(cfg)

    start = month_start(month_dt)
    end = add_month(start)
    news_start = start - timedelta(days=4)
    news_end = end

    try:
        world_articles, world_capped = fetch_gdelt_range(
            cfg.get("world_news_query", "economy"),
            news_start,
            news_end,
        )
        world_error = None
    except Exception as exc:
        world_articles, world_capped, world_error = [], 0, str(exc)

    assets_out = {}
    snapshot_count = 0

    for asset in cfg["assets"]:
        query = asset.get("history_news_query") or asset["name"]
        try:
            articles, capped = fetch_gdelt_range(query, news_start, news_end)
            news_error = None
        except Exception as exc:
            articles, capped, news_error = [], 0, str(exc)

        try:
            frame = build_frame(asset, proxies).dropna(subset=["price_score", "macro", "vol"])
            rows = []
            for pos, idx in enumerate(frame.index):
                anchor_date = pd.Timestamp(idx).date()
                if not (start.date() <= anchor_date < end.date()):
                    continue
                # Need enough future history to score the longest horizon.
                if pos + 20 >= len(frame.index):
                    continue

                cutoff = cutoff_for(anchor_date)
                news72 = window_articles(articles, cutoff, 72)
                world72 = window_articles(world_articles, cutoff, 72)
                news_score = sentiment([{"title": a["title"], "link": a["url"]} for a in news72])

                f = frame.iloc[pos]
                prob, pred = score_snapshot(
                    float(f["price_score"]),
                    float(f["macro"]),
                    float(news_score),
                    float(f["vol"]),
                )

                # First version freezes one evidence-based direction and checks
                # which horizon that signal actually predicts best.
                horizons = {
                    "next_day": future_result(frame, pos, 1, 0.002),
                    "two_days": future_result(frame, pos, 2, 0.003),
                    "one_month": future_result(frame, pos, 20, 0.010),
                }

                row = {
                    "as_of_date": anchor_date.isoformat(),
                    "information_cutoff_jst": cutoff.isoformat(),
                    "price_data_through": anchor_date.isoformat(),
                    "price": float(f["close"]),
                    "price_score": float(f["price_score"]),
                    "macro_score": float(f["macro"]),
                    "news_score": float(news_score),
                    "asset_news_count_72h": len(news72),
                    "world_news_count_72h": len(world72),
                    "asset_news_examples": [article_public(a) for a in news72[-3:]],
                    "world_news_examples": [article_public(a) for a in world72[-2:]],
                    "prediction_probability_up": prob,
                    "prediction_direction": pred,
                    "horizons": horizons,
                }
                rows.append(row)
                snapshot_count += 1

            assets_out[asset["symbol"]] = {
                "name": asset["name"],
                "kind": asset["kind"],
                "news_query": query,
                "archive_articles": len(articles),
                "archive_capped": bool(capped),
                "news_error": news_error,
                "snapshots": rows,
            }
        except Exception as exc:
            assets_out[asset["symbol"]] = {
                "name": asset["name"],
                "kind": asset["kind"],
                "news_query": query,
                "archive_articles": len(articles),
                "archive_capped": bool(capped),
                "news_error": news_error,
                "error": str(exc),
                "snapshots": [],
            }

    out = {
        "month": start.strftime("%Y-%m"),
        "generated_at": datetime.now(UTC).isoformat(),
        "purpose": "Historical replay: freeze only information visible by each date, then score future outcomes.",
        "anti_leakage": {
            "cutoff": "Each snapshot uses price data through as_of_date and news seen by 23:59:59 JST that date.",
            "future_prices": "Future closes are stored only inside horizons for later scoring and are never input features.",
            "news": "News examples are restricted to the 72 hours ending at the displayed cutoff.",
        },
        "forecast_note": "The current prototype freezes one direction signal per snapshot and scores it at 1, 2, and 20 trading-day horizons. Horizon-specific models will be trained only after enough replay months exist.",
        "world_news": {
            "archive_articles": len(world_articles),
            "archive_capped": bool(world_capped),
            "error": world_error,
        },
        "snapshot_count": snapshot_count,
        "assets": assets_out,
    }

    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    path = REPLAY_DIR / f"{start.strftime('%Y-%m')}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def update_index(progress):
    index = {
        "updated_at": datetime.now(UTC).isoformat(),
        "completed_months": progress.get("completed_months", []),
        "failed_months": progress.get("failed_months", []),
        "next_month": progress.get("next_month"),
        "oldest_month": progress.get("oldest_month"),
        "months_completed": len(progress.get("completed_months", [])),
    }
    Path("data/replay_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    progress = load_progress()
    next_month = parse_month(progress["next_month"])
    oldest = parse_month(progress["oldest_month"])

    if next_month < oldest:
        update_index(progress)
        state = load_state("data/state.json")
        if state.get("runs"):
            latest = state["runs"][-1]
            render(load_config(), latest["regime"], latest["results"], state)
        build_report()
        print("Historical replay backfill already reached the configured five-year boundary.")
        return

    label = next_month.strftime("%Y-%m")
    try:
        out = replay_month(next_month)
        if label not in progress["completed_months"]:
            progress["completed_months"].append(label)
        progress["completed_months"] = sorted(progress["completed_months"], reverse=True)
        progress["failed_months"] = [m for m in progress.get("failed_months", []) if m != label]
        progress["next_month"] = previous_month(next_month).strftime("%Y-%m")
        print("replayed", label, "snapshots", out["snapshot_count"])
    except Exception as exc:
        failures = progress.setdefault("failed_months", [])
        if label not in failures:
            failures.append(label)
        print("replay failed", label, repr(exc))
        raise
    finally:
        save_progress(progress)
        update_index(progress)
        state = load_state("data/state.json")
        if state.get("runs"):
            latest = state["runs"][-1]
            render(load_config(), latest["regime"], latest["results"], state)
        build_report()


if __name__ == "__main__":
    main()
