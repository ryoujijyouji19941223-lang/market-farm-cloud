from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
CACHE = Path("data/actual_releases/bls_cpi_release_dates.json")
URL = "https://www.bls.gov/schedule/{year}/home.htm"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTHS = {name.upper(): i for i, name in enumerate(MONTH_NAMES, 1)}
OBS_MONTH_PATTERN = "|".join(MONTH_NAMES)
REL_MONTH_PATTERN = "(?:" + "|".join(
    f"{name[:3]}(?:{name[3:]})?"
    for name in MONTH_NAMES
) + ")"


def _text(source: str) -> str:
    source = re.sub(r"<script.*?</script>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<style.*?</style>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<[^>]+>", " ", source)
    return " ".join(html.unescape(source).split())


def parse_schedule(source: str, schedule_year: int) -> dict[str, dict]:
    text = _text(source)
    # Examples:
    # Consumer Price Index, December 1997 Jan. 13 8:30 am
    # Consumer Price Indexes, January 1998 Feb. 24 8:30 am
    pattern = re.compile(
        rf"Consumer\s+Price\s+Index(?:es)?\s*,?\s*"
        rf"(?P<obs_month>{OBS_MONTH_PATTERN})\s+(?P<obs_year>\d{{4}})"
        rf".{{0,80}}?"
        rf"(?P<rel_month>{REL_MONTH_PATTERN})\.?"
        rf"\s+(?P<day>\d{{1,2}})"
        rf"(?:\s*,?\s*(?P<rel_year>\d{{4}}))?"
        rf".{{0,30}}?"
        rf"(?P<hour>\d{{1,2}}):(?P<minute>\d{{2}})\s*"
        rf"(?P<ampm>[ap])\.?m\.?",
        re.I,
    )

    out = {}
    for match in pattern.finditer(text):
        obs_month = MONTHS.get(match.group("obs_month").upper())
        obs_year = int(match.group("obs_year"))
        if obs_month is None:
            continue

        raw_rel_month = match.group("rel_month").upper()
        rel_month = next(
            (num for name, num in MONTHS.items()
             if name.startswith(raw_rel_month[:3])),
            None,
        )
        if rel_month is None:
            continue

        rel_year_raw = match.group("rel_year")
        rel_year = int(rel_year_raw) if rel_year_raw else (
            obs_year + 1 if rel_month <= obs_month else obs_year
        )

        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        if match.group("ampm").lower() == "p" and hour != 12:
            hour += 12
        if match.group("ampm").lower() == "a" and hour == 12:
            hour = 0

        released = datetime(
            rel_year, rel_month, int(match.group("day")),
            hour, minute, 0, tzinfo=ET,
        )
        period = f"{obs_year}M{obs_month:02d}"
        out[period] = {
            "available_at": released.isoformat(),
            "availability_precision": "exact_timestamp",
            "release_date_provenance": f"BLS release schedule {schedule_year}",
            "release_url": URL.format(year=schedule_year),
            "reaction_eligible": True,
        }
    return out


def _load_cache() -> dict:
    if not CACHE.exists():
        return {}
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(rows: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_cpi_release_dates(
    start_year: int = 1998,
    end_year: int | None = None,
) -> dict[str, dict]:
    end_year = end_year or datetime.now(ET).year
    cache = _load_cache()
    covered = {
        int(row["schedule_year"])
        for row in cache.values()
        if row.get("schedule_year")
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 market-farm-cloud/1.3 (+historical research)",
        "Accept": "text/html,application/xhtml+xml",
    })

    for year in range(start_year, end_year + 1):
        if year in covered:
            continue
        try:
            response = session.get(URL.format(year=year), timeout=30)
            response.raise_for_status()
            rows = parse_schedule(response.text, year)
        except Exception:
            # Fail closed. Missing release dates leave CPI observations unresolved.
            continue

        for period, row in rows.items():
            row["schedule_year"] = year
            cache[period] = row

    _save_cache(cache)
    return cache
