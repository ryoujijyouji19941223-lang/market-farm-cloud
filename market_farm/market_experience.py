from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

STORE = Path("data/market_experience")


@dataclass(frozen=True)
class MarketExperience:
    experience_id: str
    event_key: str
    information_cutoff: str
    expectation_id: str | None
    expected_value: float | None
    actual_record_id: str
    actual_available_at: str
    actual_value: float
    surprise: float | None
    surprise_direction: str
    semantic_effect: str | None
    reactions: dict
    provenance: dict


def make_experience(*, event_key: str, information_cutoff: str,
                    expectation: dict | None, actual: dict,
                    surprise: dict, semantic: dict, reactions: dict,
                    provenance: dict) -> MarketExperience:
    cutoff = datetime.fromisoformat(information_cutoff)
    actual_at = datetime.fromisoformat(actual["available_at"])
    if cutoff.tzinfo is None or actual_at.tzinfo is None:
        raise ValueError("experience timestamps must be timezone-aware")
    if cutoff < actual_at:
        raise ValueError("experience cannot include an actual release before it was public")

    exp_id = expectation.get("expectation_id") if expectation else None
    raw = "|".join((event_key, actual["record_id"], exp_id or "none"))
    eid = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return MarketExperience(
        experience_id=eid,
        event_key=event_key,
        information_cutoff=information_cutoff,
        expectation_id=exp_id,
        expected_value=float(expectation["expected_value"]) if expectation else None,
        actual_record_id=actual["record_id"],
        actual_available_at=actual["available_at"],
        actual_value=float(actual["value"]),
        surprise=surprise.get("surprise"),
        surprise_direction=surprise.get("direction", "UNKNOWN"),
        semantic_effect=semantic.get("semantic_effect"),
        reactions=dict(reactions),
        provenance=dict(provenance),
    )


def save_experiences(items: list[MarketExperience]) -> int:
    for item in items:
        month = item.actual_available_at[:7]
        path = STORE / f"{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    rows[row["experience_id"]] = row
                except Exception:
                    continue
        rows[item.experience_id] = asdict(item)
        ordered = sorted(rows.values(), key=lambda x: (x["actual_available_at"], x["experience_id"]))
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in ordered) + "\n", encoding="utf-8")
    return len(items)
