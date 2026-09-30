from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .actual_archive import load_rows, pairable
from .expectation_memory import load_all_expectations

OUT = Path("data/market_experience/experience_pairs.json")


def build_pairs() -> dict:
    expectations = load_all_expectations()
    actuals = [x for x in load_rows() if pairable(x)]
    actual_by_key = {}
    for row in actuals:
        actual_by_key.setdefault(row["event_key"], []).append(row)

    pairs = []
    unmatched = 0
    for exp in expectations:
        matches = actual_by_key.get(exp.get("event_key"), [])
        if not matches:
            unmatched += 1
            continue
        for actual in matches:
            if exp.get("unit") != actual.get("unit"):
                status = "UNIT_MISMATCH"
            elif not actual.get("available_at"):
                status = "WAITING_RELEASE_TIME"
            else:
                exp_at = datetime.fromisoformat(exp["available_at"])
                act_at = datetime.fromisoformat(actual["available_at"])
                if exp_at >= act_at:
                    status = "INVALID_TIME_ORDER"
                elif actual.get("reaction_eligible"):
                    status = "READY"
                else:
                    status = "READY_SURPRISE_ONLY"
            pairs.append({
                "event_key": exp["event_key"],
                "expectation_id": exp["expectation_id"],
                "actual_record_id": actual["record_id"],
                "status": status,
                "expectation_source": exp.get("source"),
                "actual_source": actual.get("source"),
                "expectation_available_at": exp.get("available_at"),
                "actual_available_at": actual.get("available_at"),
                "availability_precision": actual.get("availability_precision"),
            })

    counts = {}
    for pair in pairs:
        counts[pair["status"]] = counts.get(pair["status"], 0) + 1

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "expectations": len(expectations),
        "actual_first_releases": len(actuals),
        "pairs": len(pairs),
        "unmatched_expectations": unmatched,
        "status_counts": counts,
        "items": pairs,
    }


def main():
    payload = build_pairs()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "items"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
