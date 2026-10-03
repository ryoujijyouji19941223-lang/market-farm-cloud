from __future__ import annotations

import calendar
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ET = ZoneInfo("America/New_York")

VINTAGE_URLS = {
    "routput": "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/ROUTPUTQvQd.xlsx?hash=34FA1C6BF0007996E1885C8C32E3BEF9&sc_lang=en",
    "pcpi": "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/pcpiMvMd.xlsx",
    "pcpix": "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/pcpixMvMd.xlsx",
}

FREQUENCIES = {
    "routput": "quarterly",
    "pcpi": "monthly",
    "pcpix": "monthly",
}


def _get(url: str) -> bytes:
    r = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "market-farm-cloud/1.5"},
    )
    r.raise_for_status()
    return r.content


def _period(value, frequency: str) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()

    if frequency == "quarterly":
        m = re.fullmatch(r"(\d{4})\s*[:/-]?\s*Q([1-4])", text)
        if m:
            return f"{m.group(1)}Q{m.group(2)}"
    else:
        m = re.fullmatch(r"(\d{4})\s*[:/-]\s*(0?[1-9]|1[0-2])", text)
        if m:
            return f"{m.group(1)}M{int(m.group(2)):02d}"
        m = re.fullmatch(r"(\d{4})\s*[:/-]?\s*M(0?[1-9]|1[0-2])", text)
        if m:
            return f"{m.group(1)}M{int(m.group(2)):02d}"

    try:
        ts = pd.Timestamp(value)
        if frequency == "quarterly":
            return f"{ts.year}Q{ts.quarter}"
        return f"{ts.year}M{ts.month:02d}"
    except Exception:
        return None


def _vintage_label(value, frequency: str) -> tuple[int, int] | None:
    text = str(value).strip().upper().replace("_", "").replace(" ", "")

    if frequency == "quarterly":
        # Examples: ROUTPUT65Q4, 1990Q1, 1990:Q1
        m = re.search(
            r"(?:(?:ROUTPUT))?(?P<year>\d{2,4})[:]?Q(?P<period>[1-4])$",
            text,
        )
    else:
        # Examples: PCPI98M11, PCPIX05M2, 1998M11, 1998:M11
        m = re.search(
            r"(?:(?:PCPI|PCPIX))?(?P<year>\d{2,4})[:]?M(?P<period>\d{1,2})$",
            text,
        )

    if not m:
        return None

    year = int(m.group("year"))
    if year < 100:
        year += 1900 if year >= 50 else 2000
    period = int(m.group("period"))
    if frequency == "quarterly":
        if not 1 <= period <= 4:
            return None
    elif not 1 <= period <= 12:
        return None
    return year, period


def _matrix_frame(raw: bytes, frequency: str) -> pd.DataFrame:
    book = pd.ExcelFile(io.BytesIO(raw))
    for sheet in book.sheet_names:
        preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=30)
        for idx, row in preview.iterrows():
            cells = [
                str(x).strip().upper()
                for x in row.tolist()
                if not pd.isna(x)
            ]
            if any(_vintage_label(x, frequency) for x in cells):
                return pd.read_excel(book, sheet_name=sheet, header=int(idx))
    return pd.DataFrame()


def _safe_end_of_vintage(year: int, period: int, frequency: str) -> datetime:
    if frequency == "quarterly":
        month = period * 3
    else:
        month = period
    day = calendar.monthrange(year, month)[1]
    return datetime(year, month, day, 23, 59, 59, tzinfo=ET)


def conservative_first_visible_dates(
    raw: bytes,
    *,
    source_url: str,
    frequency: str,
) -> dict[str, dict]:
    """Map observation period to a safe public-availability proxy.

    Philadelphia Fed RTDSM vintage columns represent information available
    by that vintage. Vintage headers do not establish an intraday release
    timestamp here, so the final second of the vintage month/quarter is used.
    This intentionally delays the information and is never eligible for
    same-day reaction measurement.
    """
    frame = _matrix_frame(raw, frequency)
    if frame.empty or len(frame.columns) < 2:
        return {}

    period_col = frame.columns[0]
    vintage_cols = []
    for col in frame.columns[1:]:
        parsed = _vintage_label(col, frequency)
        if parsed:
            vintage_cols.append((col, parsed))
    vintage_cols.sort(key=lambda x: x[1])

    out = {}
    for _, row in frame.iterrows():
        period = _period(row[period_col], frequency)
        if not period:
            continue
        for col, (year, vintage_period) in vintage_cols:
            value = row[col]
            if pd.isna(value):
                continue
            available = _safe_end_of_vintage(
                year, vintage_period, frequency
            )
            unit_name = "quarter" if frequency == "quarterly" else "month"
            out[period] = {
                "available_at": available.isoformat(),
                "availability_precision": (
                    f"conservative_vintage_{unit_name}_end"
                ),
                "release_date_provenance": (
                    "Philadelphia Fed RTDSM public vintage; "
                    f"{unit_name}-end visibility proxy"
                ),
                "release_url": source_url,
                "reaction_eligible": False,
                "visibility_basis": "first_non_null_public_vintage",
            }
            break
    return out


def fetch_conservative_dates(code: str) -> dict[str, dict]:
    key = code.lower()
    url = VINTAGE_URLS[key]
    frequency = FREQUENCIES[key]
    return conservative_first_visible_dates(
        _get(url),
        source_url=url,
        frequency=frequency,
    )
