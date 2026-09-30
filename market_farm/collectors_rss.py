from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser
import requests

from .official_archive import make_record
from .official_collectors import Collector, register

JST = ZoneInfo("Asia/Tokyo")


def _published(entry):
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(JST)
    except Exception:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(JST)
        except Exception:
            return None


def rss_records(*, feed_url: str, authority: str, jurisdiction: str,
                source_type: str, entities=(), tags=(), **_ignored):
    r = requests.get(feed_url, timeout=30, headers={"User-Agent": "market-farm-cloud/0.6"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out = []
    for entry in feed.entries:
        available = _published(entry)
        link = entry.get("link", "")
        title = entry.get("title", "")
        if available is None or not title:
            # Unknown release time is not safe for point-in-time replay.
            continue
        out.append(make_record(
            available_at=available.isoformat(),
            authority=authority,
            source_type=source_type,
            jurisdiction=jurisdiction,
            title=title,
            url=link,
            entities=entities,
            tags=tags,
            payload={
                "feed_url": feed_url,
                "domain": urlparse(link).netloc,
                "summary": entry.get("summary", ""),
            },
        ))
    return out


# Feed URLs are isolated here so a provider change does not alter the archive schema.
# Collectors can be enabled after a feed URL has been verified in CI.
OFFICIAL_FEEDS = {
    "fed_press": {
        "authority": "Federal Reserve Board",
        "jurisdiction": "US",
        "source_type": "central_bank_release",
        "entities": ("FED",),
        "tags": ("monetary_policy", "financial_system"),
        "feed_url": "https://www.federalreserve.gov/feeds/press_all.xml",
    },
    "bls_latest": {
        "authority": "U.S. Bureau of Labor Statistics",
        "jurisdiction": "US",
        "source_type": "economic_statistics",
        "entities": ("US",),
        "tags": ("labor", "inflation", "economy"),
        "feed_url": "https://www.bls.gov/feed/bls_latest.rss",
    },
}


def _collector(name, spec):
    return Collector(
        name=name,
        authority=spec["authority"],
        collect=lambda s=spec: rss_records(**s),
    )


for _name, _spec in OFFICIAL_FEEDS.items():
    register(_collector(_name, _spec))
