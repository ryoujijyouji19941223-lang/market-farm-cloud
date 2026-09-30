from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectationSource:
    source_id: str
    authority: str
    region: str
    kind: str
    first_period: str
    cadence: str
    point_in_time_quality: str
    url: str
    notes: str


SOURCES = {
    "philadelphia_fed_spf": ExpectationSource(
        source_id="philadelphia_fed_spf",
        authority="Federal Reserve Bank of Philadelphia",
        region="US",
        kind="professional_forecaster_survey",
        first_period="1968-Q4",
        cadence="quarterly",
        point_in_time_quality="high",
        url="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/survey-of-professional-forecasters",
        notes="Official mean, median and individual forecasts; historical publication dates available.",
    ),
    "ecb_spf": ExpectationSource(
        source_id="ecb_spf",
        authority="European Central Bank",
        region="EA",
        kind="professional_forecaster_survey",
        first_period="1999",
        cadence="quarterly",
        point_in_time_quality="high",
        url="https://www.ecb.europa.eu/stats/ecb_surveys/survey_of_professional_forecasters/html/index.en.html",
        notes="Official aggregate statistics, round releases and microdata.",
    ),
    "nyfed_primary_dealers": ExpectationSource(
        source_id="nyfed_primary_dealers",
        authority="Federal Reserve Bank of New York",
        region="US",
        kind="policy_expectations_survey",
        first_period="historical_archive",
        cadence="before_fomc",
        point_in_time_quality="high",
        url="https://www.newyorkfed.org/markets/primarydealer_survey_questions",
        notes="Useful for policy-rate expectations around FOMC meetings.",
    ),
}


def source_manifest() -> dict:
    return {k: vars(v) for k, v in SOURCES.items()}
