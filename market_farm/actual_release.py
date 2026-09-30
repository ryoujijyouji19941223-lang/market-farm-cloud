from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ActualRelease:
    record_id: str
    event_key: str
    indicator: str
    value: float
    unit: str
    available_at: str
    observation_period: str
    vintage: str
    source: str
    source_url: str


def make_actual(*, record_id: str, event_key: str, indicator: str, value: float,
                unit: str, available_at: str, observation_period: str,
                vintage: str, source: str, source_url: str) -> ActualRelease:
    dt = datetime.fromisoformat(available_at)
    if dt.tzinfo is None:
        raise ValueError("actual release available_at must be timezone-aware")
    return ActualRelease(record_id, event_key, indicator, float(value), unit,
                         available_at, observation_period, vintage, source, source_url)


def validate_pair(expectation: dict, actual: ActualRelease) -> None:
    exp_time = datetime.fromisoformat(expectation["available_at"])
    act_time = datetime.fromisoformat(actual.available_at)
    if expectation["event_key"] != actual.event_key:
        raise ValueError("expectation and actual refer to different events")
    if exp_time >= act_time:
        raise ValueError("expectation was not public before the actual release")
    if expectation["unit"] != actual.unit:
        raise ValueError("expectation and actual units differ")
