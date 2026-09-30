from __future__ import annotations

import calendar
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .canonical_events import canonical_event_key
from .realtime_actuals import actual_from_vintage
from .rtds_sources import SOURCES

ET = ZoneInfo("America/New_York")


def _download(url: str) -> bytes:
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/1.0"})
    r.raise_for_status()
    return r.content


def _vintage_time(label: str) -> datetime | None:
    text = str(label).upper().replace(" ", "").replace("_", "")
    m = re.search(r"(?:(?:19|20)?(\d{2,4}))[QM](\d{1,2})$", text)
    if not m:
        return None
    raw_year = int(m.group(1))
    year = raw_year if raw_year >= 1900 else (1900 + raw_year if raw_year >= 50 else 2000 + raw_year)
    value = int(m.group(2))
    if "Q" in text[-3:]:
        month = value * 3
    else:
        month = value
    if not 1 <= month <= 12:
        return None
    day = calendar.monthrange(year, month)[1]
    return datetime(year, month, day, 23, 59, 59, tzinfo=ET)


def _quarter_period(value) -> str | None:
    text = str(value).strip().upper()
    m = re.search(r"((?:19|20)?\d{2,4})\s*Q([1-4])", text)
    if m:
        year = int(m.group(1))
        if year < 100:
            year += 1900 if year >= 50 else 2000
        return f"{year}-Q{int(m.group(2))}"
    try:
        ts = pd.Timestamp(value)
        return f"{ts.year}-Q{((ts.month - 1) // 3) + 1}"
    except Exception:
        return None


def _load_frame(raw: bytes) -> pd.DataFrame:
    book = pd.ExcelFile(io.BytesIO(raw))
    for sheet in book.sheet_names:
        frame = pd.read_excel(book, sheet_name=sheet)
        if frame.shape[1] >= 2 and not frame.empty:
            return frame
    return pd.DataFrame()


def first_release_gdp_growth(raw: bytes) -> list[dict]:
    """Derive SPF-compatible q/q annualized real GDP growth from the first visible vintage."""
    frame = _load_frame(raw)
    if frame.empty:
        return []

    period_col = frame.columns[0]
    periods = [_quarter_period(v) for v in frame[period_col]]
    vintage_cols = [(c, _vintage_time(c)) for c in frame.columns[1:]]
    vintage_cols = [(c, t) for c, t in vintage_cols if t is not None]
    vintage_cols.sort(key=lambda x: x[1])

    out = []
    seen = set()
    for pos in range(1, len(frame)):
        period = periods[pos]
        prev_period = periods[pos - 1]
        if period is None or prev_period is None:
            continue
        for col, available in vintage_cols:
            current = frame.iloc[pos][col]
            previous = frame.iloc[pos - 1][col]
            if pd.isna(current) or pd.isna(previous):
                continue
            current = float(current)
            previous = float(previous)
            if previous == 0:
                continue

            growth = ((current / previous) ** 4 - 1.0) * 100.0
            event_key = canonical_event_key("US_REAL_GDP_GROWTH", period)
            if event_key in seen:
                break
            row = actual_from_vintage(
                event_key=event_key,
                indicator="US_REAL_GDP_GROWTH",
                value=growth,
                unit="percent",
                available_at=available.isoformat(),
                observation_period=period,
                release_number=1,
                source_url=SOURCES["ROUTPUT"].page_url,
            )
            row["derivation"] = "qoq_annualized_from_first_visible_real_gdp_vintage"
            row["source_vintage_column"] = str(col)
            out.append(row)
            seen.add(event_key)
            break
    return out


def fetch_gdp_first_releases() -> list[dict]:
    source = SOURCES["ROUTPUT"]
    if not source.vintage_url:
        return []
    return first_release_gdp_growth(_download(source.vintage_url))
