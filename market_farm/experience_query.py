from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

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


def similar_events(*, cutoff: datetime, indicator: str,
                   semantic_effect: str | None = None,
                   surprise_direction: str | None = None,
                   events: list[dict] | None = None) -> list[dict]:
    rows = visible_events(cutoff, events)
    out = []
    for row in rows:
        if row.get("indicator") != indicator:
            continue
        if semantic_effect is not None and row.get("semantic_effect") != semantic_effect:
            continue
        if surprise_direction is not None and row.get("surprise_direction") != surprise_direction:
            continue
        out.append(row)
    return out


def reaction_values(events: list[dict], source_id: str, horizon: str) -> tuple[list[float], str]:
    values = []
    measure = "return"
    for event in events:
        reaction = (event.get("reactions") or {}).get(source_id) or {}
        if reaction.get("status") != "OK":
            continue
        point = (reaction.get("horizons") or {}).get(horizon)
        if not point:
            continue
        preferred = reaction.get("preferred_measure", "return")
        if preferred == "change_bps" and point.get("change_bps") is not None:
            values.append(float(point["change_bps"]))
            measure = "change_bps"
        elif point.get("return") is not None:
            values.append(float(point["return"]))
    return values, measure


def reaction_summary(events: list[dict], source_id: str, horizon: str) -> dict:
    values, measure = reaction_values(events, source_id, horizon)
    if not values:
        return {
            "sample_count": 0,
            "measure": measure,
            "mean": None,
            "median": None,
            "positive_share": None,
        }
    return {
        "sample_count": len(values),
        "measure": measure,
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "positive_share": sum(v > 0 for v in values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def analog_report(*, cutoff: datetime, indicator: str,
                  semantic_effect: str | None = None,
                  surprise_direction: str | None = None) -> dict:
    events = similar_events(
        cutoff=cutoff,
        indicator=indicator,
        semantic_effect=semantic_effect,
        surprise_direction=surprise_direction,
    )
    markets = {}
    for source_id in ("sp500", "gold_futures", "usd_jpy", "us10y"):
        markets[source_id] = {
            horizon: reaction_summary(events, source_id, horizon)
            for horizon in ("1d", "2d", "5d", "20d")
        }
    return {
        "as_of": cutoff.isoformat(),
        "indicator": indicator,
        "semantic_effect": semantic_effect,
        "surprise_direction": surprise_direction,
        "event_count": len(events),
        "markets": markets,
        "note": "Historical association only; not a causal claim or guaranteed future reaction.",
    }
