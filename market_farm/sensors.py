from __future__ import annotations
import math
import numpy as np
import pandas as pd


def pct(a, b):
    return (a / b - 1.0) if b else 0.0


def _market_date(df: pd.DataFrame) -> str:
    idx = df.index[-1]
    try:
        return idx.date().isoformat()
    except Exception:
        return str(idx)[:10]


def price_sensor(df: pd.DataFrame) -> dict:
    close = df["Close"].astype(float)
    price = float(close.iloc[-1])
    day = pct(price, float(close.iloc[-2]))
    mom5 = pct(price, float(close.iloc[-6])) if len(close) >= 6 else 0.0
    ma5 = float(close.tail(5).mean())
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())
    trend = pct(ma5, ma20)
    vol = float(close.pct_change().dropna().tail(20).std() * math.sqrt(252))
    raw = 4.0 * mom5 + 8.0 * trend
    return {
        "price": price,
        "market_date": _market_date(df),
        "day_change": day,
        "momentum5": mom5,
        "trend": trend,
        "volatility": vol,
        "price_score": float(np.tanh(raw)),
    }


def risk_adjust(score: float, volatility: float) -> float:
    penalty = min(max(volatility - 0.25, 0.0), 1.0) * 0.35
    return score * (1.0 - penalty)


def probability(score: float) -> float:
    return 1.0 / (1.0 + math.exp(-2.2 * score))


def market_regime(proxy_data: dict[str, dict]) -> dict:
    oil = proxy_data.get("oil", {}).get("momentum5", 0.0)
    vix = proxy_data.get("vix", {}).get("momentum5", 0.0)
    sp = proxy_data.get("sp500", {}).get("momentum5", 0.0)
    nikkei = proxy_data.get("nikkei", {}).get("momentum5", 0.0)
    us10y = proxy_data.get("us10y", {}).get("momentum5", 0.0)
    dxy = proxy_data.get("dxy", {}).get("momentum5", 0.0)
    return {
        "risk_off": max(-1.0, min(1.0, 4*vix - 2*sp)),
        "oil_pressure": max(-1.0, min(1.0, 5*oil)),
        "japan_risk": max(-1.0, min(1.0, -3*nikkei)),
        "usd_rate_pressure": max(-1.0, min(1.0, 4*us10y + 3*dxy)),
    }


def regime_adjustment(symbol: str, kind: str, regime: dict) -> float:
    risk = regime["risk_off"]
    oil = regime["oil_pressure"]
    usd = regime["usd_rate_pressure"]
    if symbol == "USDJPY=X":
        return 0.22*usd + 0.10*oil
    if symbol == "CHFJPY=X":
        return 0.16*risk - 0.05*usd
    if symbol == "EURJPY=X":
        return -0.05*risk + 0.04*oil
    if symbol == "GC=F":
        return 0.20*risk - 0.14*usd
    if kind == "equity":
        return -0.16*risk
    return 0.0
