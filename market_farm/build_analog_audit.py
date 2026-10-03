from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .experience_query import (
    analog_report_for_release_event,
    load_release_events,
)

OUT = Path("data/market_experience/analog_audit.json")


def build_audit(min_samples: int = 5) -> dict:
    events = load_release_events()
    status_counts = Counter()
    sample_counts = []
    rows = []

    for event in events:
        report = analog_report_for_release_event(
            event,
            events=events,
            min_samples=min_samples,
        )
        status = report["status"]
        status_counts[status] += 1
        sample_counts.append(int(report.get("event_count", 0)))
        rows.append({
            "release_event_id": event.get("release_event_id"),
            "actual_available_at": event.get("actual_available_at"),
            "semantic_effect": event.get("semantic_effect"),
            "surprise_direction": event.get("surprise_direction"),
            "regime_filters": report.get("regime_filters", {}),
            "status": status,
            "prior_analog_count": report.get("event_count", 0),
        })

    usable = status_counts.get("OK", 0)
    total = len(events)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minimum_sample": min_samples,
        "release_events": total,
        "status_counts": dict(status_counts),
        "usable_event_count": usable,
        "usable_event_share": (usable / total) if total else None,
        "prior_analog_count": {
            "min": min(sample_counts) if sample_counts else None,
            "max": max(sample_counts) if sample_counts else None,
            "mean": (
                sum(sample_counts) / len(sample_counts)
                if sample_counts else None
            ),
        },
        "rows": rows,
        "note": (
            "Walk-forward coverage audit only. Each event may use only earlier "
            "release events; no future reaction outcomes are visible."
        ),
    }


def main():
    payload = build_audit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "release_events": payload["release_events"],
        "status_counts": payload["status_counts"],
        "usable_event_share": payload["usable_event_share"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
