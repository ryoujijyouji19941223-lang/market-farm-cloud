from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from .backtest import feature_frame, clip, macro_score
from .data_source import fetch_history
from .engine import load_config
from .news import sentiment
from .sensors import risk_adjust, probability
from .state import load_state
from .dashboard import render

JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"


def parse_seen(value: str):
    if not value:
        return None
    try:
        dt = pd.to_datetime(value, utc=True)
        if pd.isna(dt):
            return None
        return dt.to_pydatetime().astimezone(JST)
    except Exception:
        return None


def fetch_gdelt_chunk(query: str, start_jst: datetime, end_jst: datetime):
    start_utc = start_jst.astimezone(UTC)
    end_utc = end_jst.astimezone(UTC)
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": "dateasc",
        "maxrecords": 250,
        "startdatetime": start_utc.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_utc.strftime("%Y%m%d%H%M%S"),
    }
    last_error = None
    for attempt in range(3):
        try:
            r = requests.get(
                GDELT_DOC,
                params=params,
                timeout=35,
                headers={"User-Agent": "market-farm-cloud/0.4"},
            )
            r.raise_for_status()
            data = r.json()
            return data.get("articles", []), len(data.get("articles", [])) >= 250
        except Exception as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GDELT request failed: {last_error}")


def fetch_gdelt_range(query: str, start_jst: datetime, end_jst: datetime):
    articles = []
    capped_chunks = 0
    cursor = start_jst
    # The recent test covers only about a month, so request the whole window at once.
    # If GDELT hits its 250-row cap we record that fact instead of silently pretending
    # the archive was exhaustive.
    while cursor < end_jst:
        chunk_end = min(cursor + timedelta(days=60), end_jst)
        items, capped = fetch_gdelt_chunk(query, cursor, chunk_end)
        capped_chunks += int(capped)
        for item in items:
            seen = parse_seen(item.get("seendate", ""))
            if seen is None:
                continue
            articles.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "domain": item.get("domain", ""),
                "language": item.get("language", ""),
                "sourcecountry": item.get("sourcecountry", ""),
                "seen_jst": seen.isoformat(),
                "_seen": seen,
            })
        cursor = chunk_end + timedelta(seconds=1)
        time.sleep(0.15)

    dedup = {}
    for a in articles:
        key = a.get("url") or (a.get("title"), a.get("seen_jst"))
        dedup[key] = a
    out = sorted(dedup.values(), key=lambda x: x["_seen"])
    return out, capped_chunks


def window_articles(articles, cutoff: datetime, hours: int = 72):
    start = cutoff - timedelta(hours=hours)
    return [a for a in articles if start <= a["_seen"] <= cutoff]


def article_public(a):
    return {
        "title": a.get("title", ""),
        "url": a.get("url", ""),
        "domain": a.get("domain", ""),
        "seen_jst": a.get("seen_jst", ""),
    }


def direction(prob: float, edge: float = 0.05):
    if prob >= 0.5 + edge:
        return "UP"
    if prob <= 0.5 - edge:
        return "DOWN"
    return "FLAT"


def actual_direction(change: float):
    if change > 0.002:
        return "UP"
    if change < -0.002:
        return "DOWN"
    return "FLAT"


def score_rows(rows, key: str):
    signals = [r for r in rows if r[key] != "FLAT"]
    correct = sum(r[key] == r["actual_direction"] for r in signals)
    return {
        "signals": len(signals),
        "correct": int(correct),
        "accuracy": (correct / len(signals)) if signals else None,
    }


def build_merged(asset, proxy_features):
    df = fetch_history(asset["symbol"], "6mo")
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
    return merged


def strict_cutoff(target_date):
    # A target such as Aug 20 may only use information known by Aug 19 23:59:59 JST.
    day_before = pd.Timestamp(target_date).date() - timedelta(days=1)
    return datetime.combine(day_before, dtime(23, 59, 59), tzinfo=JST)


def run_recent_news_backtest():
    cfg = load_config()
    days = int(cfg.get("recent_news_backtest_days", 35))

    proxy_features = {}
    for key, symbol in cfg["market_proxies"].items():
        try:
            proxy_features[key] = feature_frame(fetch_history(symbol, "6mo"))
        except Exception:
            proxy_features[key] = pd.DataFrame()

    now = datetime.now(JST)
    archive_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    archive_start = archive_end - timedelta(days=days + 7)

    try:
        world_articles, world_capped = fetch_gdelt_range(
            cfg.get("world_news_query", "economy"),
            archive_start,
            archive_end,
        )
        world_error = None
    except Exception as exc:
        world_articles, world_capped = [], 0
        world_error = str(exc)

    assets_out = {}
    all_rows = []

    for asset in cfg["assets"]:
        query = asset.get("history_news_query") or asset["name"]
        try:
            asset_articles, capped_chunks = fetch_gdelt_range(query, archive_start, archive_end)
            news_error = None
        except Exception as exc:
            asset_articles, capped_chunks = [], 0
            news_error = str(exc)

        try:
            merged = build_merged(asset, proxy_features)
            if len(merged) < 25:
                raise RuntimeError("not enough market history")

            cutoff_date = (now - timedelta(days=days)).date()
            rows = []
            idx = list(merged.index)

            for i in range(1, len(idx)):
                target_idx = idx[i]
                target_date = pd.Timestamp(target_idx).date()
                if target_date < cutoff_date:
                    continue

                feature_idx = idx[i - 1]
                feature_date = pd.Timestamp(feature_idx).date()
                f = merged.loc[feature_idx]
                if pd.isna(f["price_score"]) or pd.isna(f["vol"]) or pd.isna(f["macro"]):
                    continue

                cutoff = strict_cutoff(target_date)
                news_window = window_articles(asset_articles, cutoff, 72)
                public_news = [{"title": a["title"], "link": a["url"]} for a in news_window]
                nscore = sentiment(public_news)

                world_window = window_articles(world_articles, cutoff, 72)

                # Baseline: same long-history model that intentionally has no historical news.
                base_raw = (0.68 / 0.83) * float(f["price_score"]) + (0.15 / 0.83) * float(f["macro"])
                base_raw = risk_adjust(base_raw, float(f["vol"]))
                base_prob = probability(base_raw)
                base_pred = direction(base_prob)

                # News model: same weights as the live prototype.
                news_raw = 0.68 * float(f["price_score"]) + 0.17 * float(nscore) + 0.15 * float(f["macro"])
                news_raw = risk_adjust(news_raw, float(f["vol"]))
                news_prob = probability(news_raw)
                news_pred = direction(news_prob)

                previous_close = float(merged.loc[feature_idx, "close"])
                target_close = float(merged.loc[target_idx, "close"])
                change = target_close / previous_close - 1.0
                actual = actual_direction(change)

                row = {
                    "symbol": asset["symbol"],
                    "name": asset["name"],
                    "target_date": target_date.isoformat(),
                    "information_cutoff_jst": cutoff.isoformat(),
                    "price_data_through": feature_date.isoformat(),
                    "news_lookback_hours": 72,
                    "asset_news_count": len(news_window),
                    "world_news_count": len(world_window),
                    "asset_news_examples": [article_public(a) for a in news_window[-3:]],
                    "world_news_examples": [article_public(a) for a in world_window[-2:]],
                    "price_score": float(f["price_score"]),
                    "macro_score": float(f["macro"]),
                    "news_score": float(nscore),
                    "baseline_probability_up": float(base_prob),
                    "baseline_direction": base_pred,
                    "news_probability_up": float(news_prob),
                    "news_direction": news_pred,
                    "actual_direction": actual,
                    "actual_change": float(change),
                    "baseline_correct": bool(base_pred == actual),
                    "news_correct": bool(news_pred == actual),
                }
                rows.append(row)
                all_rows.append(row)

            assets_out[asset["symbol"]] = {
                "name": asset["name"],
                "query": query,
                "archive_articles": len(asset_articles),
                "capped_chunks": capped_chunks,
                "news_error": news_error,
                "rows": rows,
                "without_news": score_rows(rows, "baseline_direction"),
                "with_news": score_rows(rows, "news_direction"),
            }
        except Exception as exc:
            assets_out[asset["symbol"]] = {
                "name": asset["name"],
                "query": query,
                "archive_articles": len(asset_articles),
                "capped_chunks": capped_chunks,
                "news_error": news_error,
                "error": str(exc),
                "rows": [],
                "without_news": {"signals": 0, "correct": 0, "accuracy": None},
                "with_news": {"signals": 0, "correct": 0, "accuracy": None},
            }

    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": days,
        "cutoff_rule": "For target date D, use market data through the prior trading day and news seen by 23:59:59 JST on calendar day D-1.",
        "anti_leakage": {
            "price": "No target-day or later prices are used in features.",
            "news": "GDELT articles are filtered by seen_jst <= the displayed information cutoff.",
            "actual": "Target-day close is used only after the prediction is frozen, for scoring.",
        },
        "news_source": "GDELT DOC 2.0 API",
        "news_model": "Headline keyword sentiment, experimental. World-news headlines are archived for audit but not yet added to the score.",
        "world_news": {
            "query": cfg.get("world_news_query", ""),
            "archive_articles": len(world_articles),
            "capped_chunks": world_capped,
            "error": world_error,
        },
        "overall": {
            "without_news": score_rows(all_rows, "baseline_direction"),
            "with_news": score_rows(all_rows, "news_direction"),
        },
        "assets": assets_out,
    }

    Path("data").mkdir(exist_ok=True)
    Path("data/recent_news_backtest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    state = load_state("data/state.json")
    if state.get("runs"):
        latest = state["runs"][-1]
        render(cfg, latest["regime"], latest["results"], state)

    return out


def main():
    out = run_recent_news_backtest()
    print("Recent strict-cutoff news backtest")
    print("without news:", out["overall"]["without_news"])
    print("with news:", out["overall"]["with_news"])
    for row in out["assets"].values():
        print(row["name"], "news", row["archive_articles"], "with", row["with_news"], "without", row["without_news"])


if __name__ == "__main__":
    main()
