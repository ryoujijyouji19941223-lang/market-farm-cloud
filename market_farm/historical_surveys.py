from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class HistoricalSurvey:
    source_id: str
    first_year: int
    cadence: str
    reliability_note: str
    historical_url: str

SURVEYS = {
    "livingston": HistoricalSurvey(
        source_id="livingston",
        first_year=1946,
        cadence="semiannual",
        reliability_note=(
            "Official Philadelphia Fed archive. Pre-2004 base-value caveats apply; "
            "discontinued stock-price series must remain separately flagged. "
            "Variable definitions and transformations must be preserved by era."
        ),
        historical_url="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/livingston-historical-data",
    ),
    "spf": HistoricalSurvey(
        source_id="spf",
        first_year=1968,
        cadence="quarterly",
        reliability_note=(
            "Official SPF archive. Exact Philadelphia Fed publication dates are "
            "available for the modern period; older survey timing needs separate provenance."
        ),
        historical_url="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/survey-of-professional-forecasters",
    ),
}
