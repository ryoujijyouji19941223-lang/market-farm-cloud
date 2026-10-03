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
from .regime_context import inflation_context, regime_signature

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


def _attach_surprise_magnitude(events: list[dict]) -> list[dict]:
    history = defaultdict(list)
    ordered = sorted(
        events,
        key=lambda x: (x["actual_available_at"], x["release_event_id"]),
    )

    for event in ordered:
        indicator = event.get("indicator")
        raw_surprise = event.get("surprise")
        prior = history[indicator]
        context = {
            "status": "NO_SURPRISE" if raw_surprise is None else "PARTIAL_HISTORY",
            "prior_sample_count": len(prior),
            "absolute_surprise": None,
            "expanding_percentile": None,
            "magnitude_bucket": None,
            "method": "absolute surprise rank versus strictly earlier releases",
        }

        if raw_surprise is not None:
            magnitude = abs(float(raw_surprise))
            context["absolute_surprise"] = magnitude
            if prior:
                percentile = sum(x <= magnitude for x in prior) / len(prior)
                context["expanding_percentile"] = percentile
                if percentile < 1 / 3:
                    bucket = "small"
                elif percentile < 2 / 3:
                    bucket = "middle"
                else:
                    bucket = "large"
                context["magnitude_bucket"] = bucket
            if len(prior) >= 5:
                context["status"] = "OK"
            prior.append(magnitude)

        event.setdefault("post_release_context", {})[
            "surprise_magnitude"
        ] = context

    return ordered


def build_release_events() -> list[dict]:
    expectations = {x["expectation_id"]: x for x in load_all_expectations()}
    all_actual_rows = load_rows()
    actuals = {x["record_id"]: x for x in all_actual_rows}
    reaction_map = defaultdict(dict)
    for row in load_reactions():
        reaction_map[row["actual_record_id"]][row["source_id"]] = {
            "label": row.get("label"),
            "symbol": row.get("symbol"),
            "unit": row.get("unit"),
            "provenance_url": row.get("provenance_url"),
            "data_provider": row.get("data_provider"),
            "fallback": bool(row.get("fallback", False)),
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

        inflation = inflation_context(
            datetime.fromisoformat(actual["available_at"]),
            all_actual_rows,
        )
        signature = regime_signature(inflation)

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
            "pre_release_context": {
                "inflation": inflation,
                "regime_signature": signature,
            },
            "reactions": reaction_map.get(actual_id, {}),
            "causal_claim": None,
            "reaction_note": "Observed after the release; not attributed solely to this release.",
        })

    return _attach_surprise_magnitude(events)


def main():
    events = build_release_events()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in events)
        + ("\n" if events else ""),
        encoding="utf-8",
    )
    regime_quality = {}
    for event in events:
        quality = (
            event.get("pre_release_context", {})
            .get("regime_signature", {})
            .get("quality", "UNKNOWN")
        )
        regime_quality[quality] = regime_quality.get(quality, 0) + 1

    STATUS.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_events": len(events),
        "rule": "one row per actual release; latest eligible public expectation only",
        "regime_context_quality": regime_quality,
        "regime_method": "expanding point-in-time percentile thirds",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"release events={len(events)}")


if __name__ == "__main__":
    main()
