from __future__ import annotations

import io
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ET = ZoneInfo("America/New_York")
URL = (
    "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/"
    "livingston-survey/livingston-release-dates.xlsx"
    "?hash=F1B872596626611C6F8C973747D3DA37&la=en&sc_lang=en"
)


def _download() -> bytes:
    r = requests.get(
        URL,
        timeout=60,
        headers={"User-Agent": "market-farm-cloud/1.6"},
    )
    r.raise_for_status()
    return r.content


def _date(value) -> datetime | None:
    if pd.isna(value):
        return None
    try:
        ts = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    if ts.year < 1940 or ts.year > 2100:
        return None
    return datetime(
        ts.year, ts.month, ts.day,
        23, 59, 59, tzinfo=ET,
    )


def _table(book: pd.ExcelFile) -> pd.DataFrame:
    for sheet in book.sheet_names:
        preview = pd.read_excel(
            book, sheet_name=sheet, header=None, nrows=40
        )
        for idx, row in preview.iterrows():
            cells = [
                str(x).strip().upper()
                for x in row.tolist()
                if not pd.isna(x)
            ]
            if any("RELEASE" in x and "DATE" in x for x in cells):
                return pd.read_excel(
                    book, sheet_name=sheet, header=int(idx)
                )
    return pd.DataFrame()


def parse_release_dates(raw: bytes) -> dict[str, dict]:
    book = pd.ExcelFile(io.BytesIO(raw))
    frame = _table(book)
    if frame.empty:
        return {}

    release_col = next(
        (
            c for c in frame.columns
            if "RELEASE" in str(c).upper()
            and "DATE" in str(c).upper()
        ),
        None,
    )
    survey_col = next(
        (
            c for c in frame.columns
            if "SURVEY" in str(c).upper()
            and "DATE" in str(c).upper()
        ),
        None,
    )
    if release_col is None:
        return {}

    out = {}
    for _, row in frame.iterrows():
        released = _date(row[release_col])
        if released is None:
            continue

        surveyed = (
            _date(row[survey_col])
            if survey_col is not None else None
        )
        basis = surveyed or released
        key = f"{basis.year}-{basis.month:02d}"
        out[key] = {
            "available_at": released.isoformat(),
            "availability_precision": "official_date_conservative_eod",
            "release_date_provenance": (
                "Philadelphia Fed Livingston Survey release-date workbook"
            ),
            "release_url": URL,
        }
    return out


def fetch_release_dates() -> dict[str, dict]:
    return parse_release_dates(_download())
