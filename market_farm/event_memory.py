from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime


def _event_id(day: str, entities: tuple[str, ...], tags: tuple[str, ...]) -> str:
    raw = day + "|" + ",".join(entities) + "|" + ",".join(tags)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _keys(item: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    entities = tuple(sorted(set(item.get("entities") or ())))
    tags = tuple(sorted(set(item.get("tags") or ())))
    return entities, tags


def group_evidence(evidence: list[dict]) -> list[dict]:
    """Conservatively group evidence; never invent causal links.

    Items are grouped only when they share calendar day plus at least one
    explicit entity or tag. Untagged evidence remains its own event.
    """
    buckets = defaultdict(list)
    singles = []
    for item in evidence:
        day = datetime.fromisoformat(item["available_at"]).date().isoformat()
        entities, tags = _keys(item)
        if not entities and not tags:
            singles.append((day, item))
            continue
        buckets[(day, entities, tags)].append(item)

    events = []
    for (day, entities, tags), items in buckets.items():
        events.append({
            "event_id": _event_id(day, entities, tags),
            "date": day,
            "entities": list(entities),
            "tags": list(tags),
            "evidence_ids": [x["evidence_id"] for x in items],
            "evidence_count": len(items),
            "primary_evidence_count": sum(x.get("reliability") == "primary" for x in items),
            "first_available_at": min(x["available_at"] for x in items),
            "last_available_at": max(x["available_at"] for x in items),
            "causal_claim": None,
        })

    for day, item in singles:
        events.append({
            "event_id": _event_id(day, (item["evidence_id"],), ()),
            "date": day,
            "entities": [],
            "tags": [],
            "evidence_ids": [item["evidence_id"]],
            "evidence_count": 1,
            "primary_evidence_count": int(item.get("reliability") == "primary"),
            "first_available_at": item["available_at"],
            "last_available_at": item["available_at"],
            "causal_claim": None,
        })
    return sorted(events, key=lambda x: (x["first_available_at"], x["event_id"]))
