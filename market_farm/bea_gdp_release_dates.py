from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
BASE = "https://www.bea.gov"
ARCHIVE = BASE + "/news/archive?created_1=All&field_related_product_target_id=451&page={page}&title="

_QUARTERS = {
    "FIRST": 1, "1ST": 1,
    "SECOND": 2, "2ND": 2,
    "THIRD": 3, "3RD": 3,
    "FOURTH": 4, "4TH": 4,
}


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
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s+(\d{4})\b",
        text,
        re.I,
    )
    if not m:
        return None
    dt = datetime.strptime(" ".join(m.groups()), "%B %d %Y")
    # Archive table supplies a publication date, not a guaranteed intraday time.
    return dt.replace(hour=23, minute=59, second=59, tzinfo=ET)


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
        }
    return out, len(parser.rows)


def fetch_gdp_advance_dates(max_pages: int = 30) -> dict[str, dict]:
    out = {}
    for page in range(max_pages):
        url = ARCHIVE.format(page=page)
        r = requests.get(url, timeout=45, headers={"User-Agent": "market-farm-cloud/1.0"})
        r.raise_for_status()
        rows, row_count = parse_archive_page(r.text)
        if page > 0 and row_count <= 1:
            break
        before = len(out)
        out.update(rows)
        if page > 3 and not rows and len(out) == before:
            break
    return out
