from __future__ import annotations

# Mechanical interpretation only. These labels describe the data surprise,
# not a guaranteed market direction.
INDICATORS = {
    "US_CPI_YOY": {
        "above_means": "more_inflation",
        "below_means": "less_inflation",
        "themes": ["inflation", "rates"],
    },
    "US_CORE_CPI_YOY": {
        "above_means": "more_core_inflation",
        "below_means": "less_core_inflation",
        "themes": ["inflation", "rates"],
    },
    "US_UNEMPLOYMENT_RATE": {
        "above_means": "weaker_labor",
        "below_means": "stronger_labor",
        "themes": ["labor", "growth", "rates"],
    },
    "US_NONFARM_PAYROLLS": {
        "above_means": "stronger_labor",
        "below_means": "weaker_labor",
        "themes": ["labor", "growth", "rates"],
    },
    "US_REAL_GDP_GROWTH": {
        "above_means": "stronger_growth",
        "below_means": "weaker_growth",
        "themes": ["growth", "rates", "risk_assets"],
    },
    "FED_POLICY_RATE": {
        "above_means": "tighter_policy",
        "below_means": "easier_policy",
        "themes": ["monetary_policy", "rates"],
    },
    "JP_CPI_YOY": {
        "above_means": "more_inflation",
        "below_means": "less_inflation",
        "themes": ["inflation", "rates", "JPY"],
    },
    "BOJ_POLICY_RATE": {
        "above_means": "tighter_policy",
        "below_means": "easier_policy",
        "themes": ["monetary_policy", "rates", "JPY"],
    },
}


def describe_surprise(indicator: str, surprise: dict) -> dict:
    spec = INDICATORS.get(indicator)
    if spec is None or surprise.get("status") != "OK":
        return {**surprise, "semantic_effect": None, "themes": []}

    direction = surprise["direction"]
    if direction == "INLINE":
        semantic = "in_line_with_expectation"
    elif direction == "ABOVE":
        semantic = spec["above_means"]
    else:
        semantic = spec["below_means"]

    return {**surprise, "semantic_effect": semantic, "themes": spec["themes"]}
