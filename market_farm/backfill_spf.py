from __future__ import annotations

import calendar
import io
import json
from dataclasses import asdict
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .canonical_events import canonical_event_key
from .expectation_memory import Expectation, make_expectation, promote_expectation, save_expectations
from .spf_release_dates import fetch_release_dates

ET = ZoneInfo("America/New_York")
STATUS = Path("data/expectations/spf_backfill_status.json")

MEDIAN_GROWTH = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/historical-data/mediangrowth.xlsx"

# Start with the series that already has a compatible first-release actual in RTDS.
VARIABLES = {
    "RGDP": ("US_REAL_GDP_GROWTH", "percent"),
}


def _download_excel(url: str) -> bytes:
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/1.2"})
    r.raise_for_status()
    return r.content


def _survey_quarter(row: pd.Series) -> tuple[int, int] | None:
    keys = {str(k).strip().upper(): k for k in row.index}
    if "YEAR" not in keys or "QUARTER" not in keys:
        return None
    try:
        return int(row[keys["YEAR"]]), int(row[keys["QUARTER"]])
    except Exception:
        return None


def _target_from_column(name: str, variable: str, year: int, quarter: int):
    text = str(name).upper().strip()
    # Official MedianGrowth workbook uses names such as drgdp2 ... drgdp6.
    m = re.fullmatch(rf"D?{re.escape(variable)}([1-6])", text)
    if not m:
        return None
    suffix = int(m.group(1))
    # SPF convention: 1=previous quarter history, 2=current quarter,
    # 3..6=one through four quarters ahead.
    if suffix == 1:
        return None
    offset = suffix - 2
    q0 = quarter - 1 + offset
    return suffix, year + q0 // 4, q0 % 4 + 1


def _target_release_marker(year: int, quarter: int) -> datetime:
    # Conservative marker after quarter end. This is only the forecast target
    # boundary; actual first-release timestamps come from RTDS separately.
    end_month = quarter * 3
    end_day = calendar.monthrange(year, end_month)[1]
    base = pd.Timestamp(year=year, month=end_month, day=end_day) + pd.Timedelta(days=45)
    return datetime(base.year, base.month, base.day, 23, 59, 59, tzinfo=ET)


def _header_row(book: pd.ExcelFile, sheet_name: str) -> int | None:
    preview = pd.read_excel(book, sheet_name=sheet_name, header=None, nrows=25)
    for idx, row in preview.iterrows():
        cells = {str(x).strip().upper() for x in row.tolist() if not pd.isna(x)}
        if {"YEAR", "QUARTER"}.issubset(cells):
            return int(idx)
    return None


def parse_median_growth(data: bytes, release_dates: dict[str, str] | None = None) -> list:
    book = pd.ExcelFile(io.BytesIO(data))
    out = []
    release_dates = fetch_release_dates() if release_dates is None else release_dates

    for sheet_name in book.sheet_names:
        variable = str(sheet_name).strip().upper()
        if variable not in VARIABLES:
            continue
        header = _header_row(book, sheet_name)
        if header is None:
            continue
        frame = pd.read_excel(book, sheet_name=sheet_name, header=header)
        indicator, unit = VARIABLES[variable]

        for _, row in frame.iterrows():
            survey = _survey_quarter(row)
            if survey is None:
                continue
            year, quarter = survey

            for col in frame.columns:
                target = _target_from_column(col, variable, year, quarter)
                if target is None or pd.isna(row[col]):
                    continue
                _, target_year, target_quarter = target
                target_period = f"{target_year}-Q{target_quarter}"
                scheduled = _target_release_marker(target_year, target_quarter)

                # Until a verified survey-publication date is joined, keep it quarantined.
                proxy_month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
                proxy = datetime(year, proxy_month, 28, 23, 59, 59, tzinfo=ET)
                item = make_expectation(
                    event_key=canonical_event_key(indicator, target_period),
                    available_at=proxy.isoformat(),
                    scheduled_for=scheduled.isoformat(),
                    indicator=indicator,
                    jurisdiction="US",
                    expected_value=float(row[col]),
                    unit=unit,
                    source="Philadelphia Fed SPF median",
                    source_url=MEDIAN_GROWTH,
                    visibility="quarantined_release_date_proxy",
                    observation_basis="professional_forecaster_survey",
                    target_period=target_period,
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
    for sheet in book.sheet_names[:10]:
        preview = pd.read_excel(book, sheet_name=sheet, header=None, nrows=5)
        report["previews"][str(sheet)] = [
            ["" if pd.isna(value) else str(value)[:80] for value in row.tolist()[:10]]
            for _, row in preview.iterrows()
        ]
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
        "series": sorted(VARIABLES),
        "parsed": len(items),
        "saved": saved,
        "public": public_count,
        "quarantined": quarantined_count,
        "note": "Only rows with independently verified survey release dates are visible to replay.",
        "generated_at": datetime.now(ET).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SPF parsed={len(items)} saved={saved} public={public_count} quarantined={quarantined_count}")


if __name__ == "__main__":
    main()
