from __future__ import annotations

from .actual_release import validate_pair
from .indicator_semantics import describe_surprise
from .market_experience import make_experience
from .surprise import compute_surprise


def assemble_experience(*, expectation: dict, actual: dict, reactions: dict,
                        information_cutoff: str) -> object:
    # Pairing is deliberately strict: same event, same units, expectation existed first.
    from .actual_release import ActualRelease
    actual_obj = ActualRelease(
        record_id=actual["record_id"],
        event_key=actual["event_key"],
        indicator=actual["indicator"],
        value=float(actual["value"]),
        unit=actual["unit"],
        available_at=actual["available_at"],
        observation_period=actual["observation_period"],
        vintage=actual["vintage"],
        source=actual["source"],
        source_url=actual["source_url"],
    )
    validate_pair(expectation, actual_obj)

    expected = float(expectation["expected_value"])
    value = float(actual["value"])
    delta = value - expected
    surprise = {
        "status": "OK",
        "event_key": actual["event_key"],
        "expectation_id": expectation["expectation_id"],
        "expected_value": expected,
        "actual_value": value,
        "surprise": delta,
        "normalized_surprise": None,
        "unit": actual["unit"],
        "expectation_available_at": expectation["available_at"],
        "released_at": actual["available_at"],
        "direction": "ABOVE" if delta > 0 else ("BELOW" if delta < 0 else "INLINE"),
    }
    semantic = describe_surprise(actual["indicator"], surprise)

    return make_experience(
        event_key=actual["event_key"],
        information_cutoff=information_cutoff,
        expectation=expectation,
        actual=actual,
        surprise=surprise,
        semantic=semantic,
        reactions=reactions,
        provenance={
            "expectation_source": expectation.get("source"),
            "actual_source": actual.get("source"),
            "actual_vintage": actual.get("vintage"),
            "information_tier": actual.get("information_tier"),
        },
    )
