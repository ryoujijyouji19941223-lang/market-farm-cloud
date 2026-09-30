from __future__ import annotations

ALIASES = {
    "US_CPI_INFLATION": "US_CPI",
    "US_CPI_MONTHLY": "US_CPI",
    "US_CPI_LEVEL": "US_CPI",
    "US_CORE_CPI_INFLATION": "US_CORE_CPI",
    "US_NONFARM_PAYROLLS": "US_NONFARM_PAYROLLS",
    "US_REAL_GDP_GROWTH": "US_REAL_GDP",
    "US_REAL_GDP_LEVEL": "US_REAL_GDP",
    "US_UNEMPLOYMENT_RATE": "US_UNEMPLOYMENT_RATE",
}


def canonical_indicator(indicator: str) -> str:
    return ALIASES.get(indicator, indicator)


def canonical_event_key(indicator: str, target_period: str) -> str:
    if not target_period:
        raise ValueError("target_period is required for canonical event identity")
    return f"{canonical_indicator(indicator)}:{target_period}"


def expectation_event_key(row: dict) -> str:
    period = row.get("target_period")
    if not period:
        raise ValueError("expectation has no target_period")
    return canonical_event_key(row["indicator"], period)


def actual_event_key(row: dict) -> str:
    period = row.get("observation_period")
    if not period:
        raise ValueError("actual release has no observation_period")
    return canonical_event_key(row["indicator"], period)
