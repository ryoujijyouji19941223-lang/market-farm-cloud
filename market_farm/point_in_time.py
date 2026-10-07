from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Iterable

import pandas as pd


def daily_available_at(session, symbol: str) -> datetime:
    """Conservative daily-bar availability, not an exact exchange timestamp.

    Session labels are not publication times. Tokyo daily bars get an evening
    buffer; foreign/unknown markets get a next-day noon JST buffer.
    """
    day = _as_date(session)
    if symbol.endswith(".T") or symbol == "^N225":
        return datetime.combine(day, time(18), tzinfo=ZoneInfo("Asia/Tokyo"))
    return datetime.combine(day + timedelta(days=1), time(12), tzinfo=ZoneInfo("Asia/Tokyo"))


def align_daily_proxy(frame, symbol, cutoffs, target_index):
    """Use only daily proxy bars available by each target information cutoff."""
    if frame is None or frame.empty:
        return pd.Series(float("nan"), index=target_index), [None] * len(target_index)
    available = pd.DatetimeIndex([daily_available_at(idx, symbol) for idx in frame.index])
    values = pd.Series(frame["mom5"].to_numpy(), index=available).sort_index()
    stamps = pd.Series(values.index, index=values.index)
    query = pd.DatetimeIndex(cutoffs)
    selected = values.reindex(query, method="ffill")
    selected.index = target_index
    selected_times = stamps.reindex(query, method="ffill")
    return selected, [None if pd.isna(x) else x.isoformat() for x in selected_times]


def reaction_available_at(reaction: dict, horizon: str) -> datetime | None:
    """Resolve a reaction's daily session label to its market close time.

    Unknown timestamps are excluded from point-in-time training/scoring.
    This is a session-close estimate, not a verified provider arrival time.
    """
    point = (reaction.get("horizons") or {}).get(horizon) or {}
    try:
        if point.get("available_at"):
            stamp = datetime.fromisoformat(point["available_at"])
            return stamp if stamp.tzinfo is not None else None
        if not reaction.get("market_timezone") or not reaction.get("market_close") or not point.get("time"):
            return None
        clock = time.fromisoformat(reaction["market_close"])
        return datetime.combine(_as_date(point["time"]), clock, tzinfo=ZoneInfo(reaction["market_timezone"]))
    except (ValueError, TypeError, KeyError):
        return None


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
        raw = (
            article.get("_seen")
            or article.get("seen_jst")
            or article.get("seen_at")
            or article.get("published_at")
            or article.get("date")
        )
        if raw is None:
            # Unknown publication time cannot be proven point-in-time safe.
            raise FutureInformationLeak(f"{label} article has no verifiable publication timestamp")
        ts = pd.Timestamp(raw)
        if ts.tzinfo is None:
            raise FutureInformationLeak(f"{label} publication timestamp must include timezone")
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
    for label, raw in {
        "price": snapshot.get("price_available_at"),
        **(snapshot.get("proxy_available_at") or {}),
    }.items():
        if raw is not None:
            stamp = pd.Timestamp(raw)
            if stamp.tzinfo is None or stamp > cutoff:
                raise FutureInformationLeak(f"{label} has an unverified or future availability time")
    for outcome in (snapshot.get("horizons") or {}).values():
        if outcome and outcome.get("available_at"):
            if pd.Timestamp(outcome["available_at"]) <= cutoff:
                raise FutureInformationLeak("Scored outcome was already available at prediction time")
