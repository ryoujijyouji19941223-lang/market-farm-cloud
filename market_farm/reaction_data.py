from __future__ import annotations

import io
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from .reaction_sources import ReactionSource


def _fred_frame(series_id: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/1.1"})
    r.raise_for_status()
    frame = pd.read_csv(io.StringIO(r.text))
    if frame.empty or len(frame.columns) < 2:
        return pd.DataFrame(columns=["close"])
    frame.columns = ["date", "value"]
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"]).set_index("date")
    return frame.rename(columns={"value": "close"})[["close"]]


def _yfinance_frame(symbol: str, start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame:
    kwargs = {"auto_adjust": False, "progress": False}
    if start is not None:
        kwargs["start"] = start.date().isoformat()
    if end is not None:
        kwargs["end"] = (end + timedelta(days=1)).date().isoformat()
    if start is None and end is None:
        kwargs["period"] = "max"
    frame = yf.download(symbol, **kwargs)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["close"])
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    out = pd.DataFrame({"close": pd.to_numeric(close, errors="coerce")})
    out.index = pd.to_datetime(out.index)
    return out.dropna(subset=["close"])


def fetch_reaction_frame(source: ReactionSource, start: datetime | None = None,
                         end: datetime | None = None) -> pd.DataFrame:
    if source.kind == "fred":
        frame = _fred_frame(source.symbol)
        if start is not None:
            frame = frame[frame.index >= pd.Timestamp(start.date())]
        if end is not None:
            frame = frame[frame.index <= pd.Timestamp(end.date())]
        return frame
    if source.kind == "yfinance":
        return _yfinance_frame(source.symbol, start, end)
    raise ValueError(f"unsupported reaction source kind: {source.kind}")
