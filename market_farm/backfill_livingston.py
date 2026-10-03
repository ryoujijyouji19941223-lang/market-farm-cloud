from __future__ import annotations

import calendar
import io
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .canonical_events import canonical_event_key
from .expectation_memory import (
    Expectation,
    make_expectation,
    promote_expectation,
    save_expectations,
)
from .livingston_release_dates import fetch_release_dates

ET = ZoneInfo("America/New_York")
STATUS = Path("data/expectations/livingston_backfill_status.json")

MEDIAN_LEVELS = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/livingston-survey/historical-data/medians.xlsx"

VARIABLES = {
    "CPI": ("US_CPI_LEVEL", "index"),
    "UNPR": ("US_UNEMPLOYMENT_RATE", "percent"),
    "RGDPX": ("US_REAL_GDP_LEVEL", "billions_real_dollars"),
    "TBILL": ("US_TBILL_RATE", "percent"),
    "TBOND": ("US_TBOND_RATE", "percent"),
}


def download(url: str) -> bytes:
    r = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "market-farm-cloud/1.6"},
    )
    r.raise_for_status()
    return r.content


def survey_date(value) -> datetime | None:
    try:
        ts = pd.Timestamp(value)
        return datetime(
            ts.year, ts.month, ts.day,
            23, 59, 59, tzinfo=ET,
        )
    except Exception:
        return None


def target_time(survey: datetime, horizon: str) -> datetime:
    months = {
        "ZM": 0,
        "6M": 6,
        "12M": 12,
        "ZY": 0,
        "1Y": 12,
        "2Y": 24,
        "10Y": 120,
    }[horizon]
    ts = pd.Timestamp(survey) + pd.DateOffset(months=months)
    day = calendar.monthrange(ts.year, ts.month)[1]
    target = datetime(
        ts.year, ts.month, day,
        23, 59, 59, tzinfo=ET,
    )
    if target <= survey:
        # Defensive fallback for unusual workbook dates.
        next_year = ts.year + 1
        day = calendar.monthrange(next_year, ts.month)[1]
        target = datetime(
            next_year, ts.month, day,
            23, 59, 59, tzinfo=ET,
        )
    return target


def _read_sheet(book: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    preview = pd.read_excel(
        book, sheet_name=sheet_name, header=None, nrows=25
    )
    header = None
    for idx, row in preview.iterrows():
        cells = {
            str(x).strip().upper()
            for x in row.tolist()
            if not pd.isna(x)
        }
        if "DATE" in cells:
            header = int(idx)
            break
    if header is None:
        return pd.DataFrame()
    return pd.read_excel(
        book, sheet_name=sheet_name, header=header
    )


def parse_workbook(
    data: bytes,
    release_dates: dict[str, dict] | None = None,
) -> list[Expectation]:
    book = pd.ExcelFile(io.BytesIO(data))
    out = []
    release_dates = release_dates or {}

    for sheet in book.sheet_names:
        variable = sheet.strip().upper()
        if variable not in VARIABLES:
            continue
        frame = _read_sheet(book, sheet)
        if frame.empty:
            continue

        indicator, unit = VARIABLES[variable]
        date_col = next(
            (
                c for c in frame.columns
                if str(c).strip().upper() == "DATE"
            ),
            None,
        )
        if date_col is None:
            continue

        for _, row in frame.iterrows():
            survey = survey_date(row[date_col])
            if survey is None:
                continue
            survey_key = f"{survey.year}-{survey.month:02d}"

            for horizon in (
                "ZM", "6M", "12M", "ZY",
                "1Y", "2Y", "10Y",
            ):
                col = next(
                    (
                        c for c in frame.columns
                        if str(c).strip().upper()
                        == f"{variable}_{horizon}"
                    ),
                    None,
                )
                if col is None or pd.isna(row[col]):
                    continue

                target = target_time(survey, horizon)
                item = make_expectation(
                    event_key=canonical_event_key(
                        indicator,
                        target.strftime("%Y-%m"),
                    ),
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
                    target_period=target.strftime("%Y-%m"),
                )

                release = release_dates.get(survey_key)
                if release:
                    try:
                        promoted = promote_expectation(
                            asdict(item),
                            release["available_at"],
                            provenance=(
                                release.get(
                                    "release_date_provenance"
                                )
                                or "Philadelphia Fed Livingston release dates"
                            ),
                        )
                        item = Expectation(**{
                            k: promoted[k]
                            for k in Expectation.__dataclass_fields__
                        })
                    except ValueError:
                        # Fail closed if a release date is incompatible with
                        # the forecast target. Keep the row quarantined.
                        pass

                out.append(item)
    return out


def main():
    raw = download(MEDIAN_LEVELS)
    try:
        release_dates = fetch_release_dates()
        if not release_dates:
            raise RuntimeError(
                "Livingston official release-date workbook parsed zero rows"
            )
    except Exception as exc:
        release_dates = {}
        release_error = repr(exc)
    else:
        release_error = None

    items = parse_workbook(raw, release_dates)
    if not items:
        raise RuntimeError(
            "Livingston official workbook parsed zero forecasts; "
            "refusing silent empty backfill"
        )

    saved = save_expectations(items)
    public_count = sum(x.visibility == "public" for x in items)
    quarantined_count = len(items) - public_count

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "source": "Philadelphia Fed Livingston Survey",
        "parsed": len(items),
        "saved": saved,
        "release_date_rows": len(release_dates),
        "public": public_count,
        "quarantined": quarantined_count,
        "release_date_error": release_error,
        "note": (
            "Forecasts are exposed only when an official Livingston public "
            "release date can be matched to the survey month. Date-only "
            "releases are conservatively visible at end of release day."
        ),
        "generated_at": datetime.now(ET).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Livingston parsed={len(items)} saved={saved} "
        f"public={public_count} quarantined={quarantined_count} "
        f"release_dates={len(release_dates)}"
    )


if __name__ == "__main__":
    main()
