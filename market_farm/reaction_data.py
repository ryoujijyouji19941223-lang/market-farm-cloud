from __future__ import annotations

import io
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from .reaction_sources import ReactionSource

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

FRED_FALLBACKS = {
    "DEXJPUS": {
        "symbol": "JPY=X",
        "scale": 1.0,
        "provider": "yfinance_fx_proxy",
        "provenance_url": "https://finance.yahoo.com/quote/JPY=X/history/",
    },
    "DGS10": {
        "symbol": "^TNX",
        # Yahoo historical ^TNX closes are already expressed as percentage yield
        # (for example ~5.24 when the 10Y yield is ~5.24%).
        "scale": 1.0,
        "provider": "yfinance_tnx_proxy",
        "provenance_url": "https://finance.yahoo.com/quote/%5ETNX/history/",
    },
}


def _fred_frame(series_id: str, start: datetime | None = None,
                end: datetime | None = None, attempts: int = 1) -> pd.DataFrame:
    """Fetch only the reaction window needed from FRED.

    Full-history downloads occasionally time out in GitHub Actions. Limiting
    the requested date range also avoids moving unnecessary data through the
    historical-memory job.
    """
    params = {"id": series_id}
    if start is not None:
        params["cosd"] = start.date().isoformat()
    if end is not None:
        params["coed"] = end.date().isoformat()

    last_error = None
    for attempt in range(attempts):
        try:
            r = requests.get(
                FRED_CSV,
                params=params,
                timeout=(5, 8),
                headers={"User-Agent": "market-farm-cloud/1.2"},
            )
            r.raise_for_status()
            frame = pd.read_csv(io.StringIO(r.text))
            if frame.empty or len(frame.columns) < 2:
                return pd.DataFrame(columns=["close"])
            frame = frame.iloc[:, :2].copy()
            frame.columns = ["date", "value"]
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
            frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
            frame = frame.dropna(subset=["date", "value"]).set_index("date")
            out = frame.rename(columns={"value": "close"})[["close"]]
            out.attrs.update({
                "data_provider": "FRED",
                "fallback": False,
                "provenance_url": f"https://fred.stlouisfed.org/series/{series_id}",
            })
            return out
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(
        f"FRED {series_id} failed after {attempts} attempts for "
        f"{params.get('cosd', 'start')}..{params.get('coed', 'end')}: {last_error}"
    )


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
        try:
            return _fred_frame(source.symbol, start, end)
        except Exception as primary_error:
            fallback = FRED_FALLBACKS.get(source.symbol)
            if fallback is None:
                raise
            frame = _yfinance_frame(fallback["symbol"], start, end)
            if frame.empty:
                raise RuntimeError(
                    f"primary FRED source failed and fallback was empty: {primary_error}"
                )
            frame = frame.copy()
            frame["close"] = frame["close"] * float(fallback["scale"])
            frame.attrs.update({
                "data_provider": fallback["provider"],
                "fallback": True,
                "primary_error": str(primary_error),
                "provenance_url": fallback["provenance_url"],
            })
            return frame
    if source.kind == "yfinance":
        frame = _yfinance_frame(source.symbol, start, end)
        frame.attrs.update({
            "data_provider": "yfinance",
            "fallback": False,
            "provenance_url": source.provenance_url,
        })
        return frame
    raise ValueError(f"unsupported reaction source kind: {source.kind}")
