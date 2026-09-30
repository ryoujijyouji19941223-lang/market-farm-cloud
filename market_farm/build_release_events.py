from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .actual_archive import load_rows
from .build_experience_pairs import build_pairs
from .expectation_memory import load_all_expectations
from .indicator_semantics import describe_surprise
from .reaction_archive import load_reactions

OUT = Path("data/market_experience/release_events.jsonl")
STATUS = Path("data/market_experience/release_event_status.json")


def _surprise(expectation: dict, actual: dict) -> dict:
    expected = float(expectation["expected_value"])
    value = float(actual["value"])
    delta = value - expected
    direction = "ABOVE" if delta > 0 else ("BELOW" if delta < 0 else "INLINE")
    base = {
        "status": "OK",
        "direction": direction,
        "surprise": delta,
        "expected_value": expected,
        "actual_value": value,
        "unit": actual["unit"],
    }
    return describe_surprise(actual["indicator"], base)


def build_release_events() -> list[dict]:
    expectations = {x["expectation_id"]: x for x in load_all_expectations()}
    actuals = {x["record_id"]: x for x in load_rows()}
    reaction_map = defaultdict(dict)
    for row in load_reactions():
        reaction_map[row["actual_record_id"]][row["source_id"]] = {
            "label": row.get("label"),
            "symbol": row.get("symbol"),
            "unit": row.get("unit"),
            "provenance_url": row.get("provenance_url"),
            **row.get("reaction", {}),
        }

    grouped = defaultdict(list)
    for pair in build_pairs()["items"]:
        if pair["status"] not in {"READY", "READY_SURPRISE_ONLY"}:
            continue
        grouped[pair["actual_record_id"]].append(pair)

    events = []
    for actual_id, pairs in grouped.items():
        actual = actuals.get(actual_id)
        if actual is None:
            continue
        valid = [p for p in pairs if p["expectation_id"] in expectations]
        if not valid:
            continue

        # For event-level reaction research use only the latest public forecast
        # available before the actual release. Older forecasts remain in the
        # forecast-experience cards, but do not duplicate this market event.
        latest_pair = max(valid, key=lambda p: p["expectation_available_at"])
        latest = expectations[latest_pair["expectation_id"]]
        surprise = _surprise(latest, actual)

        events.append({
            "release_event_id": actual_id,
            "event_key": actual["event_key"],
            "indicator": actual["indicator"],
            "observation_period": actual["observation_period"],
            "actual_available_at": actual["available_at"],
            "actual_value": actual["value"],
            "unit": actual["unit"],
            "actual_source": actual.get("source"),
            "latest_public_expectation_id": latest["expectation_id"],
            "latest_public_expectation_at": latest["available_at"],
            "latest_public_expectation_value": latest["expected_value"],
            "expectation_source": latest.get("source"),
            "eligible_expectation_count": len(valid),
            "surprise": surprise.get("surprise"),
            "surprise_direction": surprise.get("direction"),
            "semantic_effect": surprise.get("semantic_effect"),
            "reactions": reaction_map.get(actual_id, {}),
            "causal_claim": None,
            "reaction_note": "Observed after the release; not attributed solely to this release.",
        })

    return sorted(events, key=lambda x: (x["actual_available_at"], x["release_event_id"]))


def main():
    events = build_release_events()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in events)
        + ("\n" if events else ""),
        encoding="utf-8",
    )
    STATUS.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_events": len(events),
        "rule": "one row per actual release; latest eligible public expectation only",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"release events={len(events)}")


if __name__ == "__main__":
    main()
