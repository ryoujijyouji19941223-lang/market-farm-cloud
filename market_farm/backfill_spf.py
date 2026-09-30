from __future__ import annotations

import io
import json
from dataclasses import asdict
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .expectation_memory import Expectation, make_expectation, save_expectations, promote_expectation
from .spf_release_dates import fetch_release_dates
from .canonical_events import canonical_event_key
from .event_keys import event_key

ET = ZoneInfo("America/New_York")
STATUS = Path("data/expectations/spf_backfill_status.json")

MEDIAN_GROWTH = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/historical-data/mediangrowth.xlsx"

# Deliberately start with variables whose semantics are stable and useful.
VARIABLES = {
    "CPI": ("US_CPI_INFLATION", "percent"),
    "CORECPI": ("US_CORE_CPI_INFLATION", "percent"),
    "UNEMP": ("US_UNEMPLOYMENT_RATE", "percent"),
    "RGDP": ("US_REAL_GDP_GROWTH", "percent"),
}


def _download_excel(url: str) -> bytes:
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/0.7"})
    r.raise_for_status()
    return r.content


def _survey_quarter(row: pd.Series) -> tuple[int, int] | None:
    # Philadelphia Fed historical workbooks conventionally expose YEAR/QUARTER.
    keys = {str(k).strip().upper(): k for k in row.index}
    if "YEAR" not in keys or "QUARTER" not in keys:
        return None
    try:
        return int(row[keys["YEAR"]]), int(row[keys["QUARTER"]])
    except Exception:
        return None


def _release_proxy(year: int, quarter: int) -> datetime:
    # Safety-first fallback. Exact historical release dates should replace this
    # proxy before a forecast is exposed to a daily replay.
    month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
    return datetime(year, month, 28, 23, 59, tzinfo=ET)


def _target_from_column(name: str, year: int, quarter: int):
    text = str(name).upper().strip()
    # Growth workbooks commonly use variable+horizon columns such as CPI1/CPI2.
    m = re.match(r"([A-Z]+)([1-6])$", text)
    if not m or m.group(1) not in VARIABLES:
        return None
    suffix = int(m.group(2))
    # SPF convention: 1=historical previous quarter, 2=current quarter,
    # 3..6 = one..four quarters ahead. Column 1 is not a forecast.
    if suffix == 1:
        return None
    offset = suffix - 2
    q0 = quarter - 1 + offset
    target_year = year + q0 // 4
    target_quarter = q0 % 4 + 1
    return m.group(1), suffix, target_year, target_quarter



def _header_row(book: pd.ExcelFile, sheet_name: str, required: set[str]) -> int | None:
    preview = pd.read_excel(book, sheet_name=sheet_name, header=None, nrows=25)
    wanted = {x.upper() for x in required}
    for idx, row in preview.iterrows():
        cells = {str(x).strip().upper() for x in row.tolist() if not pd.isna(x)}
        if wanted.issubset(cells):
            return int(idx)
    return None


def _sheet_variable(sheet_name: str, columns) -> str | None:
    name = str(sheet_name).strip().upper()
    if name in VARIABLES:
        return name
    normalized = [str(c).strip().upper() for c in columns]
    for variable in VARIABLES:
        if any(re.fullmatch(rf"{re.escape(variable)}[1-6]", col) for col in normalized):
            return variable
    return None

def parse_median_growth(data: bytes, release_dates: dict[str, str] | None = None) -> list:
    book = pd.ExcelFile(io.BytesIO(data))
    out = []
    release_dates = fetch_release_dates() if release_dates is None else release_dates

    for sheet_name in book.sheet_names:
        header = _header_row(book, sheet_name, {"YEAR", "QUARTER"})
        if header is None:
            continue
        frame = pd.read_excel(book, sheet_name=sheet_name, header=header)
        variable = _sheet_variable(sheet_name, frame.columns)
        if variable is None:
            continue
        for _, row in frame.iterrows():
            survey = _survey_quarter(row)
            if survey is None:
                continue
            year, quarter = survey
            available = _release_proxy(year, quarter)
            for col in frame.columns:
                target = _target_from_column(col, year, quarter)
                if target is None or pd.isna(row[col]):
                    continue
                parsed_variable, suffix, target_year, target_quarter = target
                if parsed_variable != variable:
                    continue
                indicator, unit = VARIABLES[variable]
                offset = suffix - 2
                scheduled = available + timedelta(days=max(7, (offset + 1) * 91))
                item = make_expectation(
                    event_key=event_key(indicator, f"{target_year}Q{target_quarter}"),
                    available_at=available.isoformat(),
                    scheduled_for=scheduled.isoformat(),
                    indicator=indicator,
                    jurisdiction="US",
                    expected_value=float(row[col]),
                    unit=unit,
                    source="Philadelphia Fed SPF median",
                    source_url=MEDIAN_GROWTH,
                    visibility="quarantined_release_date_proxy",
                    observation_basis="professional_forecaster_survey",
                )
                release = release_dates.get(f"{year}-Q{quarter}")
                if release:
                    promoted = promote_expectation(
                        asdict(item),
                        release,
                        provenance="philadelphia_fed_spf_release_dates",
                    )
                    item = Expectation(**{
                        k: promoted[k] for k in Expectation.__dataclass_fields__
                    })
                out.append(item)
    return out



def workbook_diagnostics(data: bytes) -> dict:
    book = pd.ExcelFile(io.BytesIO(data))
    report = {"sheet_names": list(book.sheet_names), "previews": {}}
    for sheet in book.sheet_names[:6]:
        preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=12)
        rows = []
        for _, row in preview.iloc[:, :10].iterrows():
            rows.append([
                "" if pd.isna(value) else str(value)[:80]
                for value in row.tolist()
            ])
        report["previews"][str(sheet)] = rows
    return report

def main():
    raw = _download_excel(MEDIAN_GROWTH)
    items = parse_median_growth(raw)
    if not items:
        diagnostic = json.dumps(workbook_diagnostics(raw), ensure_ascii=False)
        raise RuntimeError("SPF official workbook parsed zero forecasts; diagnostics=" + diagnostic)
    saved = save_expectations(items)
    public_count = sum(x.visibility == "public" for x in items)
    quarantined_count = len(items) - public_count
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "source": "Philadelphia Fed SPF",
        "dataset": MEDIAN_GROWTH,
        "parsed": len(items),
        "saved": saved,
        "public": public_count,
        "quarantined": quarantined_count,
        "note": (
            "Only forecasts with independently verified Philadelphia Fed release "
            "dates are public to historical replay; the rest remain quarantined."
        ),
        "generated_at": datetime.now(ET).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SPF parsed={len(items)} saved={saved} public={public_count} quarantined={quarantined_count}")


if __name__ == "__main__":
    main()
