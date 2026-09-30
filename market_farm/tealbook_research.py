from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResearchForecast:
    research_id: str
    forecast_made_at: str
    public_released_at: str
    indicator: str
    target_period: str
    value: float
    unit: str
    source: str = "Federal Reserve Tealbook/Greenbook"
    information_tier: str = "delayed_research"


def make_tealbook_forecast(*, research_id: str, forecast_made_at: str,
                           public_released_at: str, indicator: str,
                           target_period: str, value: float, unit: str) -> ResearchForecast:
    made = datetime.fromisoformat(forecast_made_at)
    released = datetime.fromisoformat(public_released_at)
    if made.tzinfo is None or released.tzinfo is None:
        raise ValueError("Tealbook timestamps must be timezone-aware")
    if released <= made:
        raise ValueError("public release must follow the internal forecast date")
    return ResearchForecast(research_id, forecast_made_at, public_released_at,
                            indicator, target_period, float(value), unit)


def eligible_for_historical_prediction(_: ResearchForecast) -> bool:
    # Intentionally hard-coded. Tealbook is a benchmark, never a historical market input.
    return False
