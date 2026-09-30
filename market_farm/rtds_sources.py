from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RTDSSource:
    code: str
    indicator: str
    unit: str
    frequency: str
    url: str
    page_url: str
    value_mode: str


SOURCES = {
    "PCPI": RTDSSource(
        code="PCPI",
        indicator="US_CPI_MONTHLY",
        unit="index_or_growth",
        frequency="monthly",
        url="https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/pcpi_first_second_third.xlsx",
        page_url="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/pcpi",
        value_mode="first_second_third",
    ),
    "EMPLOY": RTDSSource(
        code="EMPLOY",
        indicator="US_NONFARM_PAYROLLS",
        unit="thousand_employees_change",
        frequency="monthly",
        url="https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/employ_level_first_second_third.xlsx",
        page_url="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/employ",
        value_mode="first_second_third",
    ),
}
