from __future__ import annotations

import html
import io
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .actual_archive import save_rows
from .event_keys import canonical_period, event_key
from .bea_gdp_release_dates import fetch_gdp_advance_dates

ET = ZoneInfo("America/New_York")
STATUS = Path("data/actual_releases/rtdsm_status.json")

SOURCES = {
    "routput": {
        "page": "https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/routput",
        "indicator": "US_REAL_GDP_GROWTH",
        "unit": "percent",
        "frequency": "quarterly",
        "transformation": "qoq_annualized_percent",
        "spf_equivalent": True,
        "required": True,
    },
    "pcpi": {
        "page": "https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/pcpi",
        "indicator": "US_CPI_MOM_GROWTH",
        "unit": "percent",
        "frequency": "monthly",
        "transformation": "mom_annualized_percent",
        "spf_equivalent": False,
        "required": False,
    },
    "pcpix": {
        "page": "https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/pcpix",
        "indicator": "US_CORE_CPI_MOM_GROWTH",
        "unit": "percent",
        "frequency": "monthly",
        "transformation": "mom_annualized_percent",
        "spf_equivalent": False,
        "required": False,
    },
}


def _get(url: str) -> requests.Response:
    r = requests.get(url, timeout=60, headers={"User-Agent": "market-farm-cloud/0.9"})
    r.raise_for_status()
    return r


def discover_workbook(page_url: str, code: str) -> str:
    body = _get(page_url).text
    pattern = rf'href=["\']([^"\']*{re.escape(code)}_first_second_third\.xlsx[^"\']*)'
    match = re.search(pattern, body, re.I)
    if not match:
        raise RuntimeError(f"first/second/third workbook not found on {page_url}")
    return urljoin(page_url, html.unescape(match.group(1)))


def _period(value, frequency: str) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(value)
        if frequency == "quarterly":
            return f"{ts.year}Q{ts.quarter}"
        return f"{ts.year}M{ts.month:02d}"

    text = str(value).strip().upper()
    q = re.search(r"(\d{4})\s*[:/-]?\s*Q([1-4])", text)
    if q:
        return f"{q.group(1)}Q{q.group(2)}"
    m = re.search(r"(\d{4})\s*[:/-]?\s*M(0?[1-9]|1[0-2])", text)
    if m:
        return f"{m.group(1)}M{int(m.group(2)):02d}"
    try:
        ts = pd.Timestamp(value)
        if frequency == "quarterly":
            return f"{ts.year}Q{ts.quarter}"
        return f"{ts.year}M{ts.month:02d}"
    except Exception:
        return None


def _release_frame(book: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    preview = pd.read_excel(book, sheet_name=sheet_name, header=None, nrows=30)
    for idx, row in preview.iterrows():
        cells = {str(x).strip().upper() for x in row.tolist() if not pd.isna(x)}
        if {"FIRST", "SECOND", "THIRD"}.issubset(cells):
            return pd.read_excel(book, sheet_name=sheet_name, header=int(idx))
    return pd.read_excel(book, sheet_name=sheet_name)


def parse_first_releases(data: bytes, code: str, spec: dict, workbook_url: str) -> list[dict]:
    book = pd.ExcelFile(io.BytesIO(data))
    sheet = next((s for s in book.sheet_names if s.strip().upper() == "DATA"), book.sheet_names[0])
    frame = _release_frame(book, sheet)
    cols = {str(c).strip().upper(): c for c in frame.columns}
    date_col = cols.get("DATE") or cols.get("OBSERVATION") or frame.columns[0]
    first_col = cols.get("FIRST")
    if first_col is None:
        preview = [str(x) for x in frame.columns[:12]]
        raise RuntimeError(f"{code}: workbook has no First column after header scan; columns={preview}")

    out = []
    for _, row in frame.iterrows():
        period = _period(row[date_col], spec["frequency"])
        value = row[first_col]
        if not period or pd.isna(value):
            continue
        try:
            number = float(value)
        except Exception:
            continue

        key = event_key(spec["indicator"], period)
        out.append({
            "record_id": f"RTDSM:{code.upper()}:{canonical_period(period)}:r1",
            "dataset": f"rtdsm_{code}",
            "event_key": key,
            "indicator": spec["indicator"],
            "observation_period": canonical_period(period),
            "value": number,
            "unit": spec["unit"],
            "release_number": 1,
            "vintage": "first_release",
            "source": "Philadelphia Fed Real-Time Data Set for Macroeconomists",
            "source_page": spec["page"],
            "source_url": workbook_url,
            "transformation": spec["transformation"],
            "spf_equivalent": spec["spf_equivalent"],
            "available_at": None,
            "availability_precision": "unresolved",
            "information_tier": "unresolved_release_time",
            "reaction_eligible": False,
        })
    return out


def backfill_one(code: str) -> dict:
    spec = SOURCES[code]
    workbook_url = discover_workbook(spec["page"], code)
    raw = _get(workbook_url).content
    rows = parse_first_releases(raw, code, spec, workbook_url)
    if not rows:
        book = pd.ExcelFile(io.BytesIO(raw))
        sheet = next(
            (s for s in book.sheet_names if s.strip().upper() == "DATA"),
            book.sheet_names[0],
        )
        frame = _release_frame(book, sheet)
        diagnostic = {
            "sheet_names": list(book.sheet_names),
            "selected_sheet": sheet,
            "shape": list(frame.shape),
            "columns": [str(x) for x in frame.columns[:20]],
            "preview": [
                ["" if pd.isna(v) else str(v)[:80] for v in row.tolist()[:12]]
                for _, row in frame.head(8).iterrows()
            ],
        }
        raise RuntimeError(
            f"{code}: official first-release workbook parsed zero rows; "
            f"diagnostics={json.dumps(diagnostic, ensure_ascii=False)}"
        )
    promoted = 0
    if code == "routput":
        release_dates = fetch_gdp_advance_dates()
        for row in rows:
            release = release_dates.get(row["observation_period"])
            if not release:
                continue
            row.update(release)
            row["information_tier"] = "public_realtime"
            promoted += 1
    saved = save_rows(f"rtdsm_{code}", rows)
    return {
        "code": code,
        "workbook_url": workbook_url,
        "parsed": len(rows),
        "saved": saved,
        "spf_equivalent": spec["spf_equivalent"],
        "release_dates_promoted": promoted,
    }


def main():
    results, errors = [], []
    for code in SOURCES:
        try:
            results.append(backfill_one(code))
        except Exception as exc:
            errors.append({"code": code, "error": repr(exc)})
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "generated_at": datetime.now(ET).isoformat(),
        "results": results,
        "errors": errors,
        "note": (
            "First-release values are archived immediately. GDP observations with "
            "verified BEA release dates are promoted to public_realtime; exact timestamps "
            "are required before post-release reaction measurement. Others remain unresolved."
        ),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"results": results, "errors": errors}, ensure_ascii=False))
    required_errors = [
        error for error in errors
        if SOURCES.get(error["code"], {}).get("required", False)
    ]
    if required_errors:
        raise RuntimeError(f"RTDSM required backfill errors: {required_errors}")


if __name__ == "__main__":
    main()
