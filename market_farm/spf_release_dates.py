from __future__ import annotations

import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
URL = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/spf-release-dates.txt"


def fetch_release_dates() -> dict[str, str]:
    r = requests.get(URL, timeout=30, headers={"User-Agent": "market-farm-cloud/0.7"})
    r.raise_for_status()
    out = {}
    for line in r.text.splitlines():
        # Official file contains survey labels such as 1990 Q3 plus dates.
        q = re.search(r"(19|20)\d{2}\s*[: -]?Q([1-4])", line, re.I)
        dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", line)
        if not q or not dates:
            continue
        year = int(q.group(0)[:4])
        quarter = int(q.group(2))
        raw = dates[-1]
        dt = datetime.strptime(raw, "%m/%d/%Y" if len(raw.split("/")[-1]) == 4 else "%m/%d/%y")
        # Historical file supplies release dates rather than intraday timestamps.
        # End-of-day ET is conservative: replay cannot see it earlier that day.
        released = dt.replace(hour=23, minute=59, second=59, tzinfo=ET)
        out[f"{year}-Q{quarter}"] = released.isoformat()
    return out
