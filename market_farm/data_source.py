from __future__ import annotations
import pandas as pd
import yfinance as yf


def fetch_history(symbol: str, period: str = "3mo") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
    if df is None or len(df) < 8:
        raise RuntimeError(f"{symbol}: price data unavailable")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df.dropna(subset=["Close"])
