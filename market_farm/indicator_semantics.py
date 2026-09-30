from __future__ import annotations

# Mechanical semantics only. This does not assert how markets must react.
INDICATORS = {
    "US_CPI_YOY": {
        "unit": "percent",
        "higher_means": "more_inflation",
        "themes": ["inflation", "rates"],
    },
    "US_CORE_CPI_YOY": {
        "unit": "percent",
        "higher_means": "more_inflation",
        "themes": ["inflation", "rates"],
    },
    "US_UNEMPLOYMENT_RATE": {
        "unit": "percent",
        "higher_means": "weaker_labor",
        "themes": ["labor", "growth", "rates"],
    },
    "US_NONFARM_PAYROLLS": {
        "unit": "thousand_jobs",
        "higher_means": "stronger_labor",
        "themes": ["labor", "growth", "rates"],
    },
    "FED_POLICY_RATE": {
        "unit": "percent",
        "higher_means": "tighter_policy",
        "themes": ["monetary_policy", "rates"],
    },
    "JP_CPI_YOY": {
        "unit": "percent",
        "higher_means": "more_inflation",
        "themes": ["inflation", "rates", "JPY"],
    },
    "BOJ_POLICY_RATE": {
        "unit": "percent",
        "higher_means": "tighter_policy",
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
        semantic = spec["higher_means"]
    else:
        semantic = "less_" + spec["higher_means"]

    return {**surprise, "semantic_effect": semantic, "themes": spec["themes"]}
