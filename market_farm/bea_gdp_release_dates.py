from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
BASE = "https://www.bea.gov"
ARCHIVE = BASE + "/news/archive?created_1=All&field_related_product_target_id=451&page={page}&title="
CACHE = Path("data/actual_releases/bea_gdp_release_dates.json")

_QUARTERS = {
    "FIRST": 1, "1ST": 1,
    "SECOND": 2, "2ND": 2,
    "THIRD": 3, "3RD": 3,
    "FOURTH": 4, "4TH": 4,
}
_MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_row = False
        self.parts = []
        self.hrefs = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self.in_row = True
            self.parts = []
            self.hrefs = []
        elif self.in_row and tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)

    def handle_data(self, data):
        if self.in_row:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)

    def handle_endtag(self, tag):
        if tag.lower() == "tr" and self.in_row:
            self.rows.append((" ".join(self.parts), list(self.hrefs)))
            self.in_row = False


def _quarter(text: str) -> str | None:
    pattern = r"\b(FIRST|SECOND|THIRD|FOURTH|1ST|2ND|3RD|4TH)\s+QUARTER(?:\s+AND\s+YEAR)?\s+(\d{4})\b"
    m = re.search(pattern, text.upper())
    if not m:
        return None
    return f"{m.group(2)}Q{_QUARTERS[m.group(1)]}"


def _published_date(text: str) -> datetime | None:
    m = re.search(
        rf"\b({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\b",
        text,
        re.I,
    )
    if not m:
        return None
    dt = datetime.strptime(" ".join(m.groups()), "%B %d %Y")
    return dt.replace(hour=23, minute=59, second=59, tzinfo=ET)


def parse_release_timestamp(source: str) -> str | None:
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", source))
    text = " ".join(text.split())
    pattern = (
        rf"(?:EMBARGOED UNTIL RELEASE AT|FOR WIRE TRANSMISSION:)\s*"
        rf"(\d{{1,2}}):(\d{{2}})\s*([AP])\.?\s*M\.?.{{0,100}}?"
        rf"({_MONTHS}\s+\d{{1,2}},\s+\d{{4}})"
    )
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    ampm = m.group(3).upper()
    if ampm == "P" and hour != 12:
        hour += 12
    if ampm == "A" and hour == 12:
        hour = 0
    date = datetime.strptime(m.group(4), "%B %d, %Y")
    return date.replace(hour=hour, minute=minute, second=0, tzinfo=ET).isoformat()


def parse_archive_page(source: str) -> tuple[dict[str, dict], int]:
    parser = _TableRows()
    parser.feed(source)
    out = {}
    for text, hrefs in parser.rows:
        if "ADVANCE" not in text.upper():
            continue
        period = _quarter(text)
        published = _published_date(text)
        if not period or not published:
            continue
        link = next((urljoin(BASE, h) for h in hrefs if "/news/" in h), None)
        out[period] = {
            "available_at": published.isoformat(),
            "availability_precision": "official_date_conservative_eod",
            "release_date_provenance": "BEA news release archive",
            "release_url": link,
            "reaction_eligible": False,
        }
    return out, len(parser.rows)


def _load_cache() -> dict:
    if not CACHE.exists():
        return {}
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(rows: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _get(url: str) -> requests.Response:
    r = requests.get(url, timeout=45, headers={"User-Agent": "market-farm-cloud/1.0"})
    r.raise_for_status()
    return r


def fetch_gdp_advance_dates(max_pages: int = 30, resolve_exact: bool = True) -> dict[str, dict]:
    out = {}
    for page in range(max_pages):
        rows, row_count = parse_archive_page(_get(ARCHIVE.format(page=page)).text)
        if page > 0 and row_count <= 1:
            break
        out.update(rows)
        # Do not stop merely because a page has no advance estimate.
        # A page can contain only later GDP estimates; pagination ends only
        # when the archive table itself is exhausted.

    cache = _load_cache()
    for period, row in out.items():
        cached = cache.get(period)
        if cached and cached.get("release_url") == row.get("release_url"):
            if cached.get("availability_precision") == "exact_timestamp":
                out[period] = cached
                continue
        if not resolve_exact or not row.get("release_url"):
            continue
        try:
            exact = parse_release_timestamp(_get(row["release_url"]).text)
        except Exception:
            exact = None
        if exact:
            row["available_at"] = exact
            row["availability_precision"] = "exact_timestamp"
            row["release_date_provenance"] = "BEA release page embargo timestamp"
            row["reaction_eligible"] = True
        cache[period] = row
    _save_cache(cache)
    return out
