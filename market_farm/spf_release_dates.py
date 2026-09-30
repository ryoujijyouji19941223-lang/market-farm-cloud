from __future__ import annotations

import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
URL = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/spf-release-dates.txt"


def parse_release_dates(text: str) -> dict[str, str]:
    out = {}
    current_year = None
    for line in text.splitlines():
        year_match = re.search(r"\b((?:19|20)\d{2})\b", line)
        if year_match:
            current_year = int(year_match.group(1))
        quarter_match = re.search(r"\bQ([1-4])\b", line, re.I)
        dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", line)
        if current_year is None or not quarter_match or not dates:
            continue
        quarter = int(quarter_match.group(1))
        raw = dates[-1]
        fmt = "%m/%d/%Y" if len(raw.split("/")[-1]) == 4 else "%m/%d/%y"
        dt = datetime.strptime(raw, fmt)
        # The source gives a date, not an intraday timestamp. End-of-day ET
        # deliberately delays visibility rather than exposing the survey early.
        released = dt.replace(hour=23, minute=59, second=59, tzinfo=ET)
        out[f"{current_year}-Q{quarter}"] = released.isoformat()
    return out


def fetch_release_dates() -> dict[str, str]:
    r = requests.get(URL, timeout=30, headers={"User-Agent": "market-farm-cloud/1.0"})
    r.raise_for_status()
    return parse_release_dates(r.text)
