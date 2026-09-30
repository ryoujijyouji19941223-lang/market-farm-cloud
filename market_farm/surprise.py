from __future__ import annotations

from datetime import datetime

from .expectation_memory import latest_expectation


def compute_surprise(*, event_key: str, actual_value: float, released_at: str,
                     unit: str, scale: float | None = None) -> dict:
    release = datetime.fromisoformat(released_at)
    if release.tzinfo is None:
        raise ValueError("released_at must be timezone-aware")

    # Only expectations already knowable immediately before the release qualify.
    expectation = latest_expectation(event_key, release)
    if expectation is None:
        return {
            "event_key": event_key,
            "status": "NO_PRIOR_EXPECTATION",
            "actual_value": float(actual_value),
            "unit": unit,
            "released_at": released_at,
        }

    expected = float(expectation["expected_value"])
    raw = float(actual_value) - expected
    normalized = raw / scale if scale not in (None, 0) else None
    return {
        "event_key": event_key,
        "status": "OK",
        "expectation_id": expectation["expectation_id"],
        "expected_value": expected,
        "actual_value": float(actual_value),
        "surprise": raw,
        "normalized_surprise": normalized,
        "unit": unit,
        "expectation_available_at": expectation["available_at"],
        "released_at": released_at,
        "direction": "ABOVE" if raw > 0 else ("BELOW" if raw < 0 else "INLINE"),
    }
