from __future__ import annotations

from datetime import datetime

from .actual_archive import load_rows
from .expectation_memory import load_expectations


def eligible_expectations(actual: dict) -> list[dict]:
    actual_time = datetime.fromisoformat(actual["available_at"])
    out = []
    for row in load_expectations():
        if row.get("visibility") != "public":
            continue
        if row.get("event_key") != actual.get("event_key"):
            continue
        if row.get("unit") != actual.get("unit"):
            continue
        try:
            available = datetime.fromisoformat(row["available_at"])
        except Exception:
            continue
        if available >= actual_time:
            continue
        out.append(row)
    return sorted(out, key=lambda x: x["available_at"])


def pair_index() -> list[dict]:
    pairs = []
    for actual in load_rows():
        if actual.get("release_number") != 1:
            continue
        for expectation in eligible_expectations(actual):
            pairs.append({
                "event_key": actual["event_key"],
                "expectation_id": expectation["expectation_id"],
                "actual_record_id": actual["record_id"],
                "expectation_available_at": expectation["available_at"],
                "actual_available_at": actual["available_at"],
                "indicator": actual["indicator"],
                "unit": actual["unit"],
                "target_period": expectation.get("target_period"),
                "expectation_source": expectation.get("source"),
                "actual_source": actual.get("source"),
            })
    return sorted(pairs, key=lambda x: (x["actual_available_at"], x["expectation_id"]))
