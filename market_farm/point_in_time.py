from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd


class FutureInformationLeak(RuntimeError):
    """Raised when a historical replay attempts to expose future information."""


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def assert_market_frame_cutoff(frame: pd.DataFrame, cutoff: date | datetime, label: str = "market") -> None:
    """Fail closed if a feature frame contains any row after the replay cutoff."""
    if frame is None or frame.empty:
        return
    limit = _as_date(cutoff)
    future = [idx for idx in frame.index if _as_date(idx) > limit]
    if future:
        first = min(_as_date(idx) for idx in future)
        raise FutureInformationLeak(
            f"{label} contains future market data: first={first.isoformat()} cutoff={limit.isoformat()}"
        )


def assert_articles_cutoff(articles: Iterable[dict], cutoff: datetime, label: str = "news") -> None:
    """Fail closed if any article became available after the information cutoff."""
    bad = []
    for article in articles:
        raw = article.get("seen_at") or article.get("published_at") or article.get("date")
        if raw is None:
            # Unknown publication time cannot be proven point-in-time safe.
            raise FutureInformationLeak(f"{label} article has no verifiable publication timestamp")
        ts = pd.Timestamp(raw)
        if ts.tzinfo is None:
            ts = ts.tz_localize(cutoff.tzinfo)
        else:
            ts = ts.tz_convert(cutoff.tzinfo)
        if ts.to_pydatetime() > cutoff:
            bad.append((ts.to_pydatetime(), article.get("title", "")))
    if bad:
        first = min(bad, key=lambda x: x[0])
        raise FutureInformationLeak(
            f"{label} contains future news: first={first[0].isoformat()} cutoff={cutoff.isoformat()} title={first[1]!r}"
        )


@dataclass(frozen=True)
class PointInTimeRecord:
    """Economic/financial observation with the date the market could first know it."""
    value: Any
    observation_date: date
    available_at: datetime
    revised_at: datetime | None = None
    source: str | None = None


def visible_records(records: Iterable[PointInTimeRecord], cutoff: datetime) -> list[PointInTimeRecord]:
    """Return only records genuinely knowable by cutoff; never use later revisions."""
    visible = []
    for record in records:
        if record.available_at <= cutoff:
            visible.append(record)
    return visible


def assert_snapshot_metadata(snapshot: dict) -> None:
    """Check persisted replay metadata for obvious time-travel mistakes."""
    cutoff = pd.Timestamp(snapshot["information_cutoff_jst"])
    if cutoff.tzinfo is None:
        raise FutureInformationLeak("information_cutoff_jst must include timezone")
    through = _as_date(snapshot["price_data_through"])
    if through > cutoff.date():
        raise FutureInformationLeak(
            f"price_data_through={through.isoformat()} is after cutoff={cutoff.date().isoformat()}"
        )
