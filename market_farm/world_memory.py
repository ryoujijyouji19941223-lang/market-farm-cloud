from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .news_archive import load_range
from .official_archive import load_official_range, visible_official
from .event_memory import group_evidence

MEMORY = Path("data/world_memory")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    available_at: str
    source_type: str
    provider: str
    title: str
    url: str
    domain: str
    query: str
    entities: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    reliability: str = "secondary"


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def classify_source(domain: str, provider: str) -> tuple[str, str]:
    d = (domain or "").lower()
    official_markers = (
        "boj.or.jp", "federalreserve.gov", "ecb.europa.eu", "bis.org",
        "stat.go.jp", "bls.gov", "bea.gov", "sec.gov", "jpx.co.jp",
    )
    if any(x in d for x in official_markers):
        return "official", "primary"
    if provider:
        return "news", "secondary"
    return "unknown", "unknown"


def evidence_from_archive(row: dict) -> Evidence:
    source_type, reliability = classify_source(row.get("domain", ""), row.get("provider", ""))
    return Evidence(
        evidence_id=row.get("id") or _id(row.get("url", ""), row.get("seen_jst", "")),
        available_at=row["seen_jst"],
        source_type=source_type,
        provider=row.get("provider", ""),
        title=row.get("title", ""),
        url=row.get("url", ""),
        domain=row.get("domain", ""),
        query=row.get("query", ""),
        reliability=reliability,
    )


def world_as_of(cutoff: datetime, *, lookback_hours: int = 72, queries: Iterable[str] | None = None) -> dict:
    start = cutoff - timedelta(hours=lookback_hours)
    wanted = set(queries or [])
    rows = load_range(start, cutoff)
    evidence = []
    official_rows = visible_official(load_official_range(start, cutoff), cutoff)
    for row in official_rows:
        evidence.append(Evidence(
            evidence_id=row["record_id"],
            available_at=row["available_at"],
            source_type=row["source_type"],
            provider=row["authority"],
            title=row["title"],
            url=row["url"],
            domain="",
            query="official",
            entities=tuple(row.get("entities", [])),
            tags=tuple(row.get("tags", [])),
            reliability="primary",
        ))
    for row in rows:
        if wanted and row.get("query") not in wanted:
            continue
        seen = datetime.fromisoformat(row["seen_jst"])
        if seen > cutoff:
            raise RuntimeError("world memory attempted to expose future evidence")
        evidence.append(evidence_from_archive(row))

    by_reliability = {"primary": 0, "secondary": 0, "unknown": 0}
    for item in evidence:
        by_reliability[item.reliability] = by_reliability.get(item.reliability, 0) + 1

    evidence_rows = [asdict(x) for x in evidence]
    events = group_evidence(evidence_rows)

    return {
        "as_of": cutoff.isoformat(),
        "lookback_hours": lookback_hours,
        "evidence_count": len(evidence),
        "source_mix": by_reliability,
        "event_count": len(events),
        "events": events,
        "evidence": evidence_rows,
    }


def save_world_snapshot(snapshot: dict) -> Path:
    cutoff = datetime.fromisoformat(snapshot["as_of"])
    path = MEMORY / cutoff.strftime("%Y/%m/%d") / (cutoff.strftime("%H%M%S") + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
