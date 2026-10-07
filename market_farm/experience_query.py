from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from .point_in_time import reaction_available_at

STORE = Path("data/market_experience/release_events.jsonl")


def load_release_events() -> list[dict]:
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return sorted(out, key=lambda x: x.get("actual_available_at", ""))


def visible_events(cutoff: datetime, events: list[dict] | None = None) -> list[dict]:
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    rows = load_release_events() if events is None else events
    visible = []
    for row in rows:
        try:
            available = datetime.fromisoformat(row["actual_available_at"])
        except Exception:
            continue
        if available.tzinfo is None:
            continue
        if available < cutoff:
            visible.append(row)
    return visible


def _regime_matches(row: dict, filters: dict[str, str] | None) -> bool:
    if not filters:
        return True
    signature = (
        row.get("pre_release_context", {})
        .get("regime_signature", {})
    )
    for key, expected in filters.items():
        if signature.get(key) != expected:
            return False
    return True


def similar_events(
    *,
    cutoff: datetime,
    indicator: str,
    semantic_effect: str | None = None,
    surprise_direction: str | None = None,
    regime_filters: dict[str, str] | None = None,
    surprise_magnitude_bucket: str | None = None,
    events: list[dict] | None = None,
) -> list[dict]:
    rows = visible_events(cutoff, events)
    out = []
    for row in rows:
        if row.get("indicator") != indicator:
            continue
        if semantic_effect is not None and row.get("semantic_effect") != semantic_effect:
            continue
        if surprise_direction is not None and row.get("surprise_direction") != surprise_direction:
            continue
        if not _regime_matches(row, regime_filters):
            continue
        if surprise_magnitude_bucket is not None:
            bucket = (
                row.get("post_release_context", {})
                .get("surprise_magnitude", {})
                .get("magnitude_bucket")
            )
            if bucket != surprise_magnitude_bucket:
                continue
        out.append(row)
    return out


def reaction_values(
    events: list[dict],
    source_id: str,
    horizon: str,
    *,
    cutoff: datetime | None = None,
) -> tuple[list[float], str, Counter, int]:
    values = []
    measure = "return"
    providers = Counter()
    fallback_count = 0
    for event in events:
        reaction = (event.get("reactions") or {}).get(source_id) or {}
        if reaction.get("status") != "OK":
            continue
        point = (reaction.get("horizons") or {}).get(horizon)
        if not point:
            continue
        if cutoff is not None:
            available = reaction_available_at(reaction, horizon)
            if available is None or available >= cutoff:
                continue

        provider = reaction.get("data_provider") or "unknown"
        providers[provider] += 1
        if reaction.get("fallback") is True:
            fallback_count += 1

        preferred = reaction.get("preferred_measure", "return")
        if preferred == "change_bps" and point.get("change_bps") is not None:
            values.append(float(point["change_bps"]))
            measure = "change_bps"
        elif point.get("return") is not None:
            values.append(float(point["return"]))
    return values, measure, providers, fallback_count


def reaction_summary(
    events: list[dict],
    source_id: str,
    horizon: str,
    *,
    min_samples: int = 5,
    cutoff: datetime | None = None,
) -> dict:
    if min_samples < 1:
        raise ValueError("min_samples must be >= 1")

    values, measure, providers, fallback_count = reaction_values(
        events, source_id, horizon, cutoff=cutoff
    )
    count = len(values)
    base = {
        "sample_count": count,
        "minimum_required": min_samples,
        "measure": measure,
        "provider_counts": dict(providers),
        "fallback_count": fallback_count,
        "fallback_share": (fallback_count / count) if count else None,
    }

    if count < min_samples:
        return {
            **base,
            "status": "INSUFFICIENT_SAMPLE",
            "mean": None,
            "median": None,
            "positive_share": None,
            "min": None,
            "max": None,
        }

    return {
        **base,
        "status": "OK",
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "positive_share": sum(v > 0 for v in values) / count,
        "min": min(values),
        "max": max(values),
    }


def analog_report(
    *,
    cutoff: datetime,
    indicator: str,
    semantic_effect: str | None = None,
    surprise_direction: str | None = None,
    regime_filters: dict[str, str] | None = None,
    surprise_magnitude_bucket: str | None = None,
    min_samples: int = 5,
    events: list[dict] | None = None,
) -> dict:
    matched = similar_events(
        cutoff=cutoff,
        indicator=indicator,
        semantic_effect=semantic_effect,
        surprise_direction=surprise_direction,
        regime_filters=regime_filters,
        surprise_magnitude_bucket=surprise_magnitude_bucket,
        events=events,
    )
    markets = {}
    for source_id in ("sp500", "gold_futures", "usd_jpy", "us10y"):
        markets[source_id] = {
            horizon: reaction_summary(
                matched, source_id, horizon, min_samples=min_samples, cutoff=cutoff
            )
            for horizon in ("1d", "2d", "5d", "20d")
        }
    return {
        "as_of": cutoff.isoformat(),
        "indicator": indicator,
        "semantic_effect": semantic_effect,
        "surprise_direction": surprise_direction,
        "regime_filters": regime_filters or {},
        "surprise_magnitude_bucket": surprise_magnitude_bucket,
        "event_count": len(matched),
        "minimum_sample": min_samples,
        "markets": markets,
        "note": (
            "Historical association only. Regime tags use information available "
            "before each event; aggregates are suppressed below the sample threshold."
        ),
    }



def release_event_regime_filters(event: dict) -> dict[str, str]:
    signature = (
        event.get("pre_release_context", {})
        .get("regime_signature", {})
    )
    filters = {}
    if signature.get("headline_level") is not None:
        filters["headline_level"] = signature["headline_level"]
    if signature.get("headline_momentum") is not None:
        filters["headline_momentum"] = signature["headline_momentum"]
    return filters


def _analog_filter_tiers(event: dict) -> list[tuple[str, dict[str, str]]]:
    strict = release_event_regime_filters(event)
    tiers: list[tuple[str, dict[str, str]]] = []
    if (
        strict.get("headline_level") is not None
        and strict.get("headline_momentum") is not None
    ):
        tiers.append(("LEVEL_AND_MOMENTUM", dict(strict)))
    if strict.get("headline_level") is not None:
        tiers.append(("LEVEL_ONLY", {
            "headline_level": strict["headline_level"],
        }))
    tiers.append(("SURPRISE_ONLY", {}))
    return tiers


def analog_report_for_release_event(
    event: dict,
    *,
    events: list[dict] | None = None,
    min_samples: int = 5,
) -> dict:
    """Post-release reaction analogs using only earlier release events.

    Search widens through a fixed hierarchy:
      1. same headline inflation level + momentum,
      2. same headline inflation level,
      3. same surprise/semantic effect only.

    Surprise is known at the release timestamp; reaction outcomes come only
    from earlier releases.
    """
    cutoff = datetime.fromisoformat(event["actual_available_at"])
    if cutoff.tzinfo is None:
        raise ValueError("event actual_available_at must be timezone-aware")

    tiers = _analog_filter_tiers(event)
    attempts = []
    selected = None
    last_report = None

    for tier, filters in tiers:
        report = analog_report(
            cutoff=cutoff,
            indicator=event["indicator"],
            semantic_effect=event.get("semantic_effect"),
            surprise_direction=event.get("surprise_direction"),
            regime_filters=filters,
            min_samples=min_samples,
            events=events,
        )
        last_report = report
        attempts.append({
            "similarity_tier": tier,
            "regime_filters": filters,
            "event_count": report["event_count"],
        })
        if report["event_count"] >= min_samples:
            selected = report
            selected["status"] = "OK"
            selected["similarity_tier"] = tier
            break

    if selected is None:
        selected = last_report
        selected["status"] = "INSUFFICIENT_ANALOGS"
        selected["similarity_tier"] = tiers[-1][0]

    selected["release_event_id"] = event.get("release_event_id")
    selected["regime_context_missing"] = not bool(
        release_event_regime_filters(event)
    )
    selected["search_attempts"] = attempts
    return selected



def release_event_magnitude_bucket(event: dict) -> str | None:
    return (
        event.get("post_release_context", {})
        .get("surprise_magnitude", {})
        .get("magnitude_bucket")
    )


def analog_report_for_release_event_magnitude(
    event: dict,
    *,
    events: list[dict] | None = None,
    min_samples: int = 5,
) -> dict:
    """Post-release analogs using surprise magnitude, then broad fallback."""
    cutoff = datetime.fromisoformat(event["actual_available_at"])
    if cutoff.tzinfo is None:
        raise ValueError("event actual_available_at must be timezone-aware")

    bucket = release_event_magnitude_bucket(event)
    attempts = []

    if bucket is not None:
        report = analog_report(
            cutoff=cutoff,
            indicator=event["indicator"],
            semantic_effect=event.get("semantic_effect"),
            surprise_direction=event.get("surprise_direction"),
            regime_filters={},
            surprise_magnitude_bucket=bucket,
            min_samples=min_samples,
            events=events,
        )
        attempts.append({
            "similarity_tier": "SURPRISE_MAGNITUDE",
            "magnitude_bucket": bucket,
            "event_count": report["event_count"],
        })
        if report["event_count"] >= min_samples:
            report["status"] = "OK"
            report["similarity_tier"] = "SURPRISE_MAGNITUDE"
            report["release_event_id"] = event.get("release_event_id")
            report["search_attempts"] = attempts
            return report

    report = analog_report(
        cutoff=cutoff,
        indicator=event["indicator"],
        semantic_effect=event.get("semantic_effect"),
        surprise_direction=event.get("surprise_direction"),
        regime_filters={},
        surprise_magnitude_bucket=None,
        min_samples=min_samples,
        events=events,
    )
    attempts.append({
        "similarity_tier": "SURPRISE_ONLY",
        "magnitude_bucket": None,
        "event_count": report["event_count"],
    })
    report["status"] = (
        "OK" if report["event_count"] >= min_samples
        else "INSUFFICIENT_ANALOGS"
    )
    report["similarity_tier"] = "SURPRISE_ONLY"
    report["release_event_id"] = event.get("release_event_id")
    report["search_attempts"] = attempts
    return report
