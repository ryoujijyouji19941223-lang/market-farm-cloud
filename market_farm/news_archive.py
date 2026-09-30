from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
ARCHIVE = Path("data/news_archive")
MANIFEST = ARCHIVE / "manifest.json"


def _month_key(seen_jst: str) -> str:
    return str(seen_jst)[:7]


def _story_id(item: dict) -> str:
    raw = (item.get("url") or "") + "\n" + (item.get("title") or "") + "\n" + (item.get("seen_jst") or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def public_record(item: dict, *, source: str, query: str, fetched_at: str | None = None) -> dict:
    seen = item.get("seen_jst")
    if not seen:
        raise ValueError("Historical news must have seen_jst")
    return {
        "id": _story_id(item),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "domain": item.get("domain", ""),
        "language": item.get("language", ""),
        "sourcecountry": item.get("sourcecountry", ""),
        "seen_jst": seen,
        "provider": source,
        "query": query,
        "fetched_at": fetched_at or datetime.now(JST).isoformat(),
    }


def save_articles(items: list[dict], *, source: str, query: str) -> int:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        record = public_record(item, source=source, query=query)
        grouped.setdefault(_month_key(record["seen_jst"]), []).append(record)

    saved = 0
    for month, records in grouped.items():
        path = ARCHIVE / f"{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    existing[row["id"]] = row
                except Exception:
                    continue
        for row in records:
            existing[row["id"]] = row
        ordered = sorted(existing.values(), key=lambda x: (x["seen_jst"], x["id"]))
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in ordered) + ("\n" if ordered else ""), encoding="utf-8")
        saved += len(records)
    return saved


def load_range(start_jst: datetime, end_jst: datetime, *, query: str | None = None) -> list[dict]:
    out = []
    if not ARCHIVE.exists():
        return out
    for path in sorted(ARCHIVE.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                seen = datetime.fromisoformat(row["seen_jst"])
            except Exception:
                continue
            if start_jst <= seen <= end_jst and (query is None or row.get("query") == query):
                row["_seen"] = seen
                out.append(row)
    return sorted(out, key=lambda x: x["_seen"])


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"ranges": {}}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {"ranges": {}}


def range_key(query: str, start_jst: datetime, end_jst: datetime) -> str:
    raw = query + "|" + start_jst.isoformat() + "|" + end_jst.isoformat()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def range_status(query: str, start_jst: datetime, end_jst: datetime) -> dict | None:
    return load_manifest().get("ranges", {}).get(range_key(query, start_jst, end_jst))


def record_range(query: str, start_jst: datetime, end_jst: datetime, *, status: str, article_count: int, provider: str, error: str | None = None):
    manifest = load_manifest()
    key = range_key(query, start_jst, end_jst)
    manifest.setdefault("ranges", {})[key] = {
        "query": query,
        "start_jst": start_jst.isoformat(),
        "end_jst": end_jst.isoformat(),
        "status": status,
        "article_count": int(article_count),
        "provider": provider,
        "error": error,
        "updated_at": datetime.now(JST).isoformat(),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
