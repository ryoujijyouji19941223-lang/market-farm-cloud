from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from .actual_release import ActualRelease, make_actual
from .information_tiers import PUBLIC_REALTIME


def actual_from_vintage(*, event_key: str, indicator: str, value: float, unit: str,
                        available_at: str, observation_period: str, release_number: int,
                        source_url: str) -> dict:
    actual = make_actual(
        record_id=f"RTDSM:{indicator}:{observation_period}:r{release_number}",
        event_key=event_key,
        indicator=indicator,
        value=value,
        unit=unit,
        available_at=available_at,
        observation_period=observation_period,
        vintage=f"release_{release_number}",
        source="Philadelphia Fed Real-Time Data Set",
        source_url=source_url,
    )
    row = asdict(actual)
    row["information_tier"] = PUBLIC_REALTIME.tier
    row["release_number"] = release_number
    return row


def choose_first_release(rows: list[dict], event_key: str) -> dict | None:
    candidates = [
        row for row in rows
        if row.get("event_key") == event_key and row.get("release_number") == 1
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda x: datetime.fromisoformat(x["available_at"]))
