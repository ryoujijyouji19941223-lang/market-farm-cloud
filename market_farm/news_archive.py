from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
ARCHIVE = Path("data/news_archive")


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
