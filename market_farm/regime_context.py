from __future__ import annotations

from datetime import datetime
from statistics import median

from .actual_archive import load_rows

SERIES = {
    "headline_cpi": "US_CPI_MOM_GROWTH",
    "core_cpi": "US_CORE_CPI_MOM_GROWTH",
}


def _aware(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("historical context timestamps must be timezone-aware")
    return dt


def _series_context(rows: list[dict], indicator: str, cutoff: datetime) -> dict:
    visible = []
    for row in rows:
        if row.get("indicator") != indicator:
            continue
        if row.get("release_number") != 1:
            continue
        if row.get("information_tier") != "public_realtime":
            continue
        raw_time = row.get("available_at")
        if not raw_time:
            continue
        try:
            available = _aware(raw_time)
            value = float(row["value"])
        except Exception:
            continue

        # Strictly before the event. A CPI release occurring at the same
        # timestamp must not become its own pre-release context.
        if available >= cutoff:
            continue
        visible.append((available, value, row))

    visible.sort(key=lambda x: (x[0], x[2].get("observation_period", "")))
    if not visible:
        return {
            "status": "NO_POINT_IN_TIME_DATA",
            "observations": 0,
        }

    values = [x[1] for x in visible]
    latest_time, latest_value, latest_row = visible[-1]

    recent = values[-3:]
    previous = values[-6:-3]
    recent_median = median(recent) if len(recent) == 3 else None
    previous_median = median(previous) if len(previous) == 3 else None
    momentum = (
        recent_median - previous_median
        if recent_median is not None and previous_median is not None
        else None
    )

    rolling_medians = [
        median(values[i - 2:i + 1])
        for i in range(2, len(values))
    ]
    percentile = None
    if recent_median is not None and rolling_medians:
        percentile = (
            sum(x <= recent_median for x in rolling_medians)
            / len(rolling_medians)
        )

    momentum_history = []
    for end in range(5, len(values)):
        left = median(values[end - 5:end - 2])
        right = median(values[end - 2:end + 1])
        momentum_history.append(right - left)

    momentum_percentile = None
    if momentum is not None and momentum_history:
        momentum_percentile = (
            sum(x <= momentum for x in momentum_history)
            / len(momentum_history)
        )

    precision_counts = {}
    for _, _, item in visible:
        precision = item.get("availability_precision") or "unknown"
        precision_counts[precision] = precision_counts.get(precision, 0) + 1

    age_days = (cutoff - latest_time).total_seconds() / 86400.0

    return {
        "status": "OK" if len(recent) == 3 else "PARTIAL_HISTORY",
        "observations": len(visible),
        "latest_value": latest_value,
        "latest_observation_period": latest_row.get("observation_period"),
        "latest_available_at": latest_time.isoformat(),
        "latest_availability_precision": latest_row.get("availability_precision"),
        "latest_release_provenance": latest_row.get("release_date_provenance"),
        "recent_3m_median": recent_median,
        "previous_3m_median": previous_median,
        "three_month_momentum": momentum,
        "expanding_percentile": percentile,
        "momentum_percentile": momentum_percentile,
        "latest_age_days": age_days,
        "availability_precision_counts": precision_counts,
        "unit": latest_row.get("unit"),
        "transformation": latest_row.get("transformation"),
    }


def inflation_context(
    cutoff: datetime,
    rows: list[dict] | None = None,
) -> dict:
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    rows = load_rows() if rows is None else rows
    out = {"cutoff": cutoff.isoformat()}
    out.update({
        name: _series_context(rows, indicator, cutoff)
        for name, indicator in SERIES.items()
    })
    return out



def _third_band(value: float | None, *, labels: tuple[str, str, str]) -> str | None:
    if value is None:
        return None
    if value < 1 / 3:
        return labels[0]
    if value < 2 / 3:
        return labels[1]
    return labels[2]


def regime_signature(context: dict) -> dict:
    """Mechanical, point-in-time regime tags derived only from prior data.

    These are descriptive lookup keys, not causal or predictive claims.
    """
    headline = context.get("headline_cpi", {})
    core = context.get("core_cpi", {})

    headline_level = _third_band(
        headline.get("expanding_percentile"),
        labels=("low", "middle", "high"),
    )
    headline_momentum = _third_band(
        headline.get("momentum_percentile"),
        labels=("cooling", "mixed", "heating"),
    )
    core_level = _third_band(
        core.get("expanding_percentile"),
        labels=("low", "middle", "high"),
    )
    core_momentum = _third_band(
        core.get("momentum_percentile"),
        labels=("cooling", "mixed", "heating"),
    )

    series_ready = {
        "headline_cpi": headline.get("status") == "OK",
        "core_cpi": core.get("status") == "OK",
    }
    ready_count = sum(series_ready.values())
    quality = "FULL" if ready_count == 2 else ("PARTIAL" if ready_count == 1 else "MISSING")

    return {
        "quality": quality,
        "series_ready": series_ready,
        "headline_level": headline_level,
        "headline_momentum": headline_momentum,
        "core_level": core_level,
        "core_momentum": core_momentum,
        "method": "expanding point-in-time percentile thirds",
        "causal_claim": None,
    }
