from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReactionSource:
    source_id: str
    label: str
    kind: str
    symbol: str
    unit: str
    timezone: str
    close_hour: int
    close_minute: int
    provenance_url: str
    notes: str


SOURCES = {
    "usd_jpy": ReactionSource(
        source_id="usd_jpy",
        label="USD/JPY",
        kind="fred",
        symbol="DEXJPUS",
        unit="jpy_per_usd",
        timezone="America/New_York",
        close_hour=17,
        close_minute=0,
        provenance_url="https://fred.stlouisfed.org/series/DEXJPUS",
        notes="Federal Reserve H.10 daily exchange-rate series; available from 1971.",
    ),
    "us10y": ReactionSource(
        source_id="us10y",
        label="US 10Y Treasury yield",
        kind="fred",
        symbol="DGS10",
        unit="percent",
        timezone="America/New_York",
        close_hour=16,
        close_minute=0,
        provenance_url="https://fred.stlouisfed.org/series/DGS10",
        notes="Federal Reserve H.15 daily constant-maturity Treasury yield.",
    ),
    "sp500": ReactionSource(
        source_id="sp500",
        label="S&P 500",
        kind="yfinance",
        symbol="^GSPC",
        unit="index",
        timezone="America/New_York",
        close_hour=16,
        close_minute=0,
        provenance_url="https://finance.yahoo.com/quote/%5EGSPC/history/",
        notes="Historical vendor series used for reaction measurement, not prediction input.",
    ),
    "gold_futures": ReactionSource(
        source_id="gold_futures",
        label="Gold futures",
        kind="yfinance",
        symbol="GC=F",
        unit="usd_per_troy_ounce",
        timezone="America/New_York",
        close_hour=17,
        close_minute=0,
        provenance_url="https://finance.yahoo.com/quote/GC%3DF/history/",
        notes="COMEX gold futures proxy. Kept distinct from spot gold.",
    ),
}
