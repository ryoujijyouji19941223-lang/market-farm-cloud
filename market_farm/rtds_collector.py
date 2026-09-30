from __future__ import annotations

import io
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .realtime_actuals import actual_from_vintage
from .rtds_sources import SOURCES
from .canonical_events import canonical_event_key

ET = ZoneInfo("America/New_York")


def _download(url: str) -> bytes:
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/0.9"})
    r.raise_for_status()
    return r.content


def _normalize_period(value) -> str:
    text = str(value).strip()
    if text.lower() in {"nan", "none", ""}:
        return ""
    try:
        ts = pd.Timestamp(value)
        if not pd.isna(ts):
            return ts.strftime("%Y-%m")
    except Exception:
        pass
    return text


def _release_time_from_row(row: pd.Series) -> str | None:
    # Prefer an explicit release-date column if the workbook includes one.
    for col in row.index:
        name = str(col).strip().upper().replace(" ", "_")
        if "RELEASE" in name and "DATE" in name and not pd.isna(row[col]):
            try:
                ts = pd.Timestamp(row[col])
                return datetime(ts.year, ts.month, ts.day, 23, 59, 59, tzinfo=ET).isoformat()
            except Exception:
                continue
    return None


def _find_column(frame: pd.DataFrame, candidates: tuple[str, ...]):
    normalized = {
        str(c).strip().upper().replace(" ", "").replace("_", ""): c
        for c in frame.columns
    }
    for candidate in candidates:
        key = candidate.upper().replace(" ", "").replace("_", "")
        if key in normalized:
            return normalized[key]
    return None


def parse_first_releases(code: str, raw: bytes) -> list[dict]:
    source = SOURCES[code]
    book = pd.ExcelFile(io.BytesIO(raw))
    rows_out = []

    for sheet in book.sheet_names:
        frame = pd.read_excel(book, sheet_name=sheet)
        if frame.empty:
            continue

        period_col = _find_column(frame, ("DATE", "PERIOD", "OBSERVATION", "OBSERVATION_DATE"))
        first_col = _find_column(frame, ("FIRST", "FIRST_RELEASE", "FIRSTVALUE", "FIRST_VALUE"))
        if period_col is None or first_col is None:
            continue

        for _, row in frame.iterrows():
            if pd.isna(row[first_col]):
                continue
            period = _normalize_period(row[period_col])
            if not period:
                continue
            release_at = _release_time_from_row(row)
            if release_at is None:
                # Do not guess a historical public timestamp.
                continue

            event_key = canonical_event_key(source.indicator, period)
            actual = actual_from_vintage(
                event_key=event_key,
                indicator=source.indicator,
                value=float(row[first_col]),
                unit=source.unit,
                available_at=release_at,
                observation_period=period,
                release_number=1,
                source_url=source.page_url,
            )
            rows_out.append(actual)

    return rows_out


def fetch_first_releases(code: str) -> list[dict]:
    return parse_first_releases(code, _download(SOURCES[code].url))


def fetch_registered_first_releases() -> dict[str, list[dict]]:
    return {code: fetch_first_releases(code) for code in SOURCES}
