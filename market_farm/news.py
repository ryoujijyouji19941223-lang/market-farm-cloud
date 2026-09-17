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
    return [{"title": e.get("title", ""), "link": e.get("link", "")} for e in feed.entries[:limit]]


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
    query = " OR ".join(asset.get("keywords", [])[:3])
    if not query:
        return [], 0.0
    items = google_news_rss(query)
    return items, sentiment(items)
