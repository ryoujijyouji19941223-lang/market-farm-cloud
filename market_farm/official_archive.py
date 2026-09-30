from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
STORE = Path("data/official_archive")


@dataclass(frozen=True)
class OfficialRecord:
    record_id: str
    available_at: str
    observed_at: str | None
    revised_at: str | None
    authority: str
    source_type: str
    jurisdiction: str
    title: str
    url: str
    entities: tuple[str, ...]
    tags: tuple[str, ...]
    payload: dict


def _id(authority: str, url: str, available_at: str, title: str) -> str:
    raw = "|".join((authority, url, available_at, title))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def make_record(*, available_at: str, authority: str, source_type: str,
                jurisdiction: str, title: str, url: str,
                observed_at: str | None = None, revised_at: str | None = None,
                entities=(), tags=(), payload=None) -> OfficialRecord:
    if datetime.fromisoformat(available_at).tzinfo is None:
        raise ValueError("available_at must be timezone-aware")
    return OfficialRecord(
        record_id=_id(authority, url, available_at, title),
        available_at=available_at,
        observed_at=observed_at,
        revised_at=revised_at,
        authority=authority,
        source_type=source_type,
        jurisdiction=jurisdiction,
        title=title,
        url=url,
        entities=tuple(entities),
        tags=tuple(tags),
        payload=dict(payload or {}),
    )


def save_records(records: list[OfficialRecord]) -> int:
    grouped = {}
    for record in records:
        month = record.available_at[:7]
        grouped.setdefault(month, []).append(asdict(record))
    for month, rows in grouped.items():
        path = STORE / f"{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    existing[row["record_id"]] = row
                except Exception:
                    continue
        for row in rows:
            existing[row["record_id"]] = row
        ordered = sorted(existing.values(), key=lambda x: (x["available_at"], x["record_id"]))
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in ordered) + "\n", encoding="utf-8")
    return len(records)


def load_official_range(start: datetime, end: datetime) -> list[dict]:
    out = []
    if not STORE.exists():
        return out
    for path in sorted(STORE.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                available = datetime.fromisoformat(row["available_at"])
            except Exception:
                continue
            if start <= available <= end:
                out.append(row)
    return sorted(out, key=lambda x: x["available_at"])


def visible_official(records: list[dict], cutoff: datetime) -> list[dict]:
    visible = []
    for row in records:
        available = datetime.fromisoformat(row["available_at"])
        if available > cutoff:
            continue
        # A later revision is not substituted for the original release.
        visible.append(row)
    return visible
