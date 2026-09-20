from __future__ import annotations
import urllib.parse
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


def fetch_asset_news(asset: dict):
    query = asset.get("news_query") or " OR ".join(asset.get("keywords", [])[:4])
    if not query:
        return [], 0.0
    items = google_news_rss(query)

    filtered = []
    for item in items:
        ok, reason = is_relevant_item(asset, item)
        if not ok:
            continue
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

    identity_match = any(term in title.lower() for term in required) if required else True
    source_match = any(term in source_url.lower() or term in source.lower() for term in trusted) if trusted else False

    if required or trusted:
        if source_match:
            return True, "trusted_source"
        if identity_match:
            return True, "identity_match"
        return False, "identity_not_verified"

    return True, "topic_match"
