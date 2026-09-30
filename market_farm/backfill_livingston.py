from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .expectation_memory import make_expectation, save_expectations

ET = ZoneInfo("America/New_York")
STATUS = Path("data/expectations/livingston_backfill_status.json")

# The Philadelphia Fed may change download filenames. Keep URLs isolated here.
MEDIAN_LEVELS = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/livingston-survey/historical-data/medians.xlsx"

VARIABLES = {
    "CPI": ("US_CPI_LEVEL", "index"),
    "UNPR": ("US_UNEMPLOYMENT_RATE", "percent"),
    "RGDPX": ("US_REAL_GDP_LEVEL", "billions_real_dollars"),
    "TBILL": ("US_TBILL_RATE", "percent"),
    "TBOND": ("US_TBOND_RATE", "percent"),
}


def download(url: str) -> bytes:
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/0.8"})
    r.raise_for_status()
    return r.content


def survey_date(value) -> datetime | None:
    try:
        ts = pd.Timestamp(value)
        return datetime(ts.year, ts.month, ts.day, 23, 59, 59, tzinfo=ET)
    except Exception:
        return None


def target_time(survey: datetime, horizon: str) -> datetime:
    months = {"ZM": 0, "6M": 6, "12M": 12, "ZY": 0, "1Y": 12, "2Y": 24, "10Y": 120}[horizon]
    ts = pd.Timestamp(survey) + pd.DateOffset(months=months)
    # Forecast target marker, not the later realized-data release timestamp.
    return datetime(ts.year, ts.month, 28, 23, 59, 59, tzinfo=ET)



def _read_sheet(book: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    preview = pd.read_excel(book, sheet_name=sheet_name, header=None, nrows=25)
    header = None
    for idx, row in preview.iterrows():
        cells = {str(x).strip().upper() for x in row.tolist() if not pd.isna(x)}
        if "DATE" in cells:
            header = int(idx)
            break
    if header is None:
        return pd.DataFrame()
    return pd.read_excel(book, sheet_name=sheet_name, header=header)

def parse_workbook(data: bytes) -> list:
    book = pd.ExcelFile(io.BytesIO(data))
    out = []
    for sheet in book.sheet_names:
        variable = sheet.strip().upper()
        if variable not in VARIABLES:
            continue
        frame = _read_sheet(book, sheet)
        if frame.empty:
            continue
        indicator, unit = VARIABLES[variable]
        date_col = next((c for c in frame.columns if str(c).strip().upper() == "DATE"), None)
        if date_col is None:
            continue
        for _, row in frame.iterrows():
            survey = survey_date(row[date_col])
            if survey is None:
                continue
            for horizon in ("ZM", "6M", "12M", "ZY", "1Y", "2Y", "10Y"):
                col = next((c for c in frame.columns if str(c).strip().upper() == f"{variable}_{horizon}"), None)
                if col is None or pd.isna(row[col]):
                    continue
                target = target_time(survey, horizon)
                if target <= survey:
                    target = target.replace(year=target.year + 1)
                out.append(make_expectation(
                    event_key=f"LIVINGSTON:{indicator}:{survey.date()}:{horizon}",
                    available_at=survey.isoformat(),
                    scheduled_for=target.isoformat(),
                    indicator=indicator,
                    jurisdiction="US",
                    expected_value=float(row[col]),
                    unit=unit,
                    source="Philadelphia Fed Livingston Survey median",
                    source_url=MEDIAN_LEVELS,
                    visibility="quarantined_release_date_proxy",
                    observation_basis="professional_forecaster_survey",
                ))
    return out


def main():
    raw = download(MEDIAN_LEVELS)
    items = parse_workbook(raw)
    if not items:
        raise RuntimeError("Livingston official workbook parsed zero forecasts; refusing silent empty backfill")
    saved = save_expectations(items)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "source": "Philadelphia Fed Livingston Survey",
        "parsed": len(items),
        "saved": saved,
        "visibility": "quarantined_release_date_proxy",
        "note": "Historical survey date is retained, but replay exposure waits for verified public release dates.",
        "generated_at": datetime.now(ET).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Livingston parsed={len(items)} saved={saved}; quarantined pending verified release dates")


if __name__ == "__main__":
    main()
