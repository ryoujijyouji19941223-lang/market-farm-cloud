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
    "pcpi": "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/pcpiMvMd.xlsx",
    "pcpix": "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/pcpixMvMd.xlsx",
}


def _get(url: str) -> bytes:
    r = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "market-farm-cloud/1.4"},
    )
    r.raise_for_status()
    return r.content


def _period(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    m = re.fullmatch(r"(\d{4})\s*[:/-]\s*(0?[1-9]|1[0-2])", text)
    if m:
        return f"{m.group(1)}M{int(m.group(2)):02d}"
    try:
        ts = pd.Timestamp(value)
        return f"{ts.year}M{ts.month:02d}"
    except Exception:
        return None


def _vintage_month(value) -> tuple[int, int] | None:
    text = str(value).strip().upper().replace("_", "").replace(" ", "")
    # Examples: PCPI98M11, PCPIX05M2, 1998M11, 1998:M11
    m = re.search(r"(?:(?:PCPI|PCPIX))?(?P<year>\d{2,4})[:]?M(?P<month>\d{1,2})$", text)
    if not m:
        return None
    year = int(m.group("year"))
    if year < 100:
        year += 1900 if year >= 50 else 2000
    month = int(m.group("month"))
    if not 1 <= month <= 12:
        return None
    return year, month


def _matrix_frame(raw: bytes) -> pd.DataFrame:
    book = pd.ExcelFile(io.BytesIO(raw))
    for sheet in book.sheet_names:
        preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=30)
        for idx, row in preview.iterrows():
            cells = [str(x).strip().upper() for x in row.tolist() if not pd.isna(x)]
            if any(_vintage_month(x) for x in cells):
                return pd.read_excel(book, sheet_name=sheet, header=int(idx))
    return pd.DataFrame()


def conservative_first_visible_dates(raw: bytes, *, source_url: str) -> dict[str, dict]:
    """Map observation period to a safe public-availability proxy.

    The Philadelphia Fed says a vintage column is public at its vintage date.
    The workbook header identifies only a vintage month, not an intraday release
    time. Therefore use that month's final second in New York as a conservative
    visibility time. This deliberately delays information and is never eligible
    for same-day reaction measurement.
    """
    frame = _matrix_frame(raw)
    if frame.empty or len(frame.columns) < 2:
        return {}

    period_col = frame.columns[0]
    vintage_cols = []
    for col in frame.columns[1:]:
        parsed = _vintage_month(col)
        if parsed:
            vintage_cols.append((col, parsed))
    vintage_cols.sort(key=lambda x: x[1])

    out = {}
    for _, row in frame.iterrows():
        period = _period(row[period_col])
        if not period:
            continue
        for col, (year, month) in vintage_cols:
            value = row[col]
            if pd.isna(value):
                continue
            day = calendar.monthrange(year, month)[1]
            available = datetime(
                year, month, day, 23, 59, 59, tzinfo=ET
            )
            out[period] = {
                "available_at": available.isoformat(),
                "availability_precision": "conservative_vintage_month_end",
                "release_date_provenance": (
                    "Philadelphia Fed RTDSM monthly vintage; month-end visibility proxy"
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
    return conservative_first_visible_dates(_get(url), source_url=url)
