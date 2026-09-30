from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

STORE = Path("data/expectations")


@dataclass(frozen=True)
class Expectation:
    expectation_id: str
    event_key: str
    available_at: str
    scheduled_for: str
    indicator: str
    jurisdiction: str
    expected_value: float
    unit: str
    source: str
    source_url: str
    visibility: str
    observation_basis: str
    sample_size: int | None = None
    low: float | None = None
    high: float | None = None


def _aware(value: str, field: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return dt


def make_expectation(*, event_key: str, available_at: str, scheduled_for: str,
                     indicator: str, jurisdiction: str, expected_value: float,
                     unit: str, source: str, source_url: str,
                     visibility: str = "public", observation_basis: str = "survey",
                     sample_size=None, low=None, high=None) -> Expectation:
    available = _aware(available_at, "available_at")
    scheduled = _aware(scheduled_for, "scheduled_for")
    if available >= scheduled:
        raise ValueError("expectation must be known before the scheduled release")
    raw = "|".join((event_key, available_at, indicator, source, str(expected_value)))
    eid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return Expectation(eid, event_key, available_at, scheduled_for, indicator,
                       jurisdiction, float(expected_value), unit, source,
                       source_url, visibility, observation_basis, sample_size, low, high)


def save_expectations(items: list[Expectation]) -> int:
    for item in items:
        month = item.scheduled_for[:7]
        path = STORE / f"{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    existing[row["expectation_id"]] = row
                except Exception:
                    continue
        existing[item.expectation_id] = asdict(item)
        rows = sorted(existing.values(), key=lambda x: (x["scheduled_for"], x["available_at"]))
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
    return len(items)


def visible_expectations(start: datetime, cutoff: datetime) -> list[dict]:
    out = []
    if not STORE.exists():
        return out
    for path in sorted(STORE.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                available = _aware(row["available_at"], "available_at")
                scheduled = _aware(row["scheduled_for"], "scheduled_for")
            except Exception:
                continue
            if start <= available <= cutoff and available < scheduled:
                out.append(row)
    return sorted(out, key=lambda x: x["available_at"])


def latest_expectation(event_key: str, cutoff: datetime) -> dict | None:
    rows = [x for x in visible_expectations(datetime.min.replace(tzinfo=cutoff.tzinfo), cutoff)
            if x["event_key"] == event_key]
    return max(rows, key=lambda x: x["available_at"]) if rows else None
