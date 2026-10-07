from __future__ import annotations
import urllib.parse
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests
import feedparser

POS = ["上昇","増益","最高益","利上げ","需要増","好調","上方修正","受注増","買い","growth","beats","upgrade","strong demand"]
NEG = ["下落","減益","赤字","下方修正","需要減","売り","訴訟","不正","景気後退","falls","misses","downgrade","recession","weak demand"]


def google_news_rss(query: str, limit: int = 8):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
    r = requests.get(url, timeout=12, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.text)
    if feed.get("bozo") or not feed.get("version"):
        raise RuntimeError("News RSS could not be parsed")
    out = []
    for e in feed.entries[:limit]:
        source = e.get("source", {}) or {}
        out.append({
            "title": e.get("title", ""),
            "link": e.get("link", ""),
            "published_at": e.get("published", "") or e.get("updated", ""),
            "source": source.get("title", "") if hasattr(source, "get") else "",
            "source_url": source.get("href", "") if hasattr(source, "get") else "",
            "summary": e.get("summary", "") or e.get("description", ""),
        })
    return out


def sentiment(items):
    if not items:
        return 0.0
    score = 0
    for item in items:
        t = item["title"].lower()
        score += sum(1 for w in POS if w.lower() in t)
        score -= sum(1 for w in NEG if w.lower() in t)
    return max(-1.0, min(1.0, score / max(4, len(items))))


def _story_key(title: str):
    title = re.sub(r"\s+-\s+[^-]+$", "", title or "")
    return re.sub(r"\s+", " ", title).strip().lower()


def fetch_asset_news(asset: dict, *, cutoff: datetime | None = None):
    cutoff = cutoff or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        raise ValueError("news cutoff must be timezone-aware")
    query = asset.get("news_query") or " OR ".join(asset.get("keywords", [])[:4])
    if not query:
        raise RuntimeError("No news query configured")
    items = google_news_rss(query)

    filtered = []
    seen = set()
    noise = ["掲示板", "株価・株式情報", "時系列", "チャート"]
    for item in items:
        title = item.get("title", "")
        if asset.get("kind") == "equity" and any(x in title for x in noise):
            continue
        ok, reason = is_relevant_item(asset, item)
        if not ok:
            continue
        # A frozen morning prediction must not include a later article.
        try:
            published = parsedate_to_datetime(item.get("published_at", ""))
        except (TypeError, ValueError, OverflowError):
            raise RuntimeError("Relevant news has no verifiable publication timestamp")
        if published.tzinfo is None:
            raise RuntimeError("News publication timestamp has no timezone")
        if published > cutoff:
            continue
        key = _story_key(title)
        if key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["relevance_reason"] = reason
        filtered.append(item)

    return filtered, sentiment(filtered)


def is_relevant_item(asset: dict, item: dict):
    title = item.get("title", "")
    source = item.get("source", "")
    source_url = item.get("source_url", "")
    haystack = f"{title} {source} {source_url}".lower()

    excluded = [x.lower() for x in asset.get("news_exclude_terms", [])]
    if excluded and any(term in haystack for term in excluded):
        return False, "excluded_term"

    required = [x.lower() for x in asset.get("news_required_any", [])]
    trusted = [x.lower() for x in asset.get("news_trusted_sources", [])]

    def matches(term):
        if re.fullmatch(r"[a-z0-9]+", term):
            return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", title.lower()) is not None
        return term in title.lower()

    identity_match = any(matches(term) for term in required) if required else True
    host = urllib.parse.urlparse(source_url).hostname or ""
    source_match = any(host == term or host.endswith("." + term) for term in trusted)

    if required or trusted:
        if source_match:
            return True, "trusted_source"
        if identity_match:
            return True, "identity_match"
        return False, "identity_not_verified"

    return True, "topic_match"
