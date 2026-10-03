import io

import pandas as pd

from market_farm.backfill_spf import _target_from_column
from market_farm.backfill_rtdsm import parse_first_releases, SOURCES
from market_farm.event_keys import event_key
from market_farm.spf_release_dates import parse_release_dates
from market_farm.bea_gdp_release_dates import parse_release_timestamp
from market_farm.bls_cpi_release_dates import parse_schedule
from market_farm.rtdsm_vintage_dates import conservative_first_visible_dates
from market_farm.livingston_release_dates import parse_release_dates as parse_livingston_release_dates
from market_farm.backfill_livingston import target_time


def test_spf_suffix_two_is_current_quarter():
    assert _target_from_column("RGDP2", 2005, 3) == ("RGDP", 2, 2005, 3)


def test_spf_suffix_six_is_four_quarters_ahead():
    assert _target_from_column("RGDP6", 2005, 3) == ("RGDP", 6, 2006, 3)


def test_spf_suffix_one_is_historical_not_forecast():
    assert _target_from_column("RGDP1", 2005, 3) is None


def test_rtdsm_first_release_matches_canonical_spf_event():
    frame = pd.DataFrame({
        "Date": ["2012:Q2", "2012:Q3"],
        "First": [1.537, 2.014],
        "Second": [1.732, 2.672],
        "Third": [1.253, 3.106],
        "Most_Recent": [2.0, 3.0],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="DATA", index=False)

    rows = parse_first_releases(
        buf.getvalue(),
        "routput",
        SOURCES["routput"],
        "https://example.test/routput.xlsx",
    )
    assert rows[0]["event_key"] == event_key("US_REAL_GDP_GROWTH", "2012Q2")
    assert rows[0]["value"] == 1.537
    assert rows[0]["availability_precision"] == "unresolved"
    assert rows[0]["reaction_eligible"] is False


def test_spf_release_date_parser_carries_year_forward():
    text = """
1991 Q1             2/16/91             2/21/91
     Q2             5/18/91             5/24/91
     Q3             8/18/91             8/21/91
"""
    rows = parse_release_dates(text)
    assert "1991-Q1" in rows
    assert "1991-Q2" in rows
    assert "1991-Q3" in rows
    assert rows["1991-Q2"].startswith("1991-05-24")


def test_bea_release_timestamp_parser():
    html = """
    <p>FOR WIRE TRANSMISSION: 8:30 A.M. EDT, FRIDAY, OCTOBER 27, 2000</p>
    """
    value = parse_release_timestamp(html)
    assert value.startswith("2000-10-27T08:30:00")


def test_cpi_first_release_workbook_without_second_third_columns():
    frame = pd.DataFrame({
        "Date": ["2012:02", "2012:03"],
        "First": [3.25, 2.11],
        "Most_Recent": [3.10, 2.00],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="DATA", index=False, startrow=2)

    rows = parse_first_releases(
        buf.getvalue(),
        "pcpi",
        SOURCES["pcpi"],
        "https://example.test/pcpi.xlsx",
    )
    assert len(rows) == 2
    assert rows[0]["event_key"] == event_key("US_CPI_MOM_GROWTH", "2012M02")
    assert rows[0]["value"] == 3.25


def test_bls_cpi_schedule_parser_handles_abbreviated_release_month():
    source = """
    <html><body>
    Consumer Price Index, December 1997 Jan. 13 8:30 am
    Consumer Price Indexes, January 1998 Feb. 24 8:30 am
    </body></html>
    """
    rows = parse_schedule(source, 1998)
    assert rows["1997M12"]["available_at"].startswith("1998-01-13T08:30:00")
    assert rows["1998M01"]["available_at"].startswith("1998-02-24T08:30:00")
    assert rows["1998M01"]["reaction_eligible"] is True


def test_cpi_vintage_month_end_is_safe_visibility_proxy():
    frame = pd.DataFrame({
        "Date": ["1998:10", "1998:11"],
        "PCPI98M11": [164.0, None],
        "PCPI98M12": [164.0, 164.4],
        "PCPI99M1": [164.0, 164.4],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="DATA", index=False, startrow=2)

    rows = conservative_first_visible_dates(
        buf.getvalue(),
        source_url="https://example.test/pcpi-vintages.xlsx",
        frequency="monthly",
    )

    oct_row = rows["1998M10"]
    nov_row = rows["1998M11"]
    assert oct_row["available_at"].startswith("1998-11-30T23:59:59")
    assert nov_row["available_at"].startswith("1998-12-31T23:59:59")
    assert oct_row["reaction_eligible"] is False
    assert oct_row["availability_precision"] == "conservative_vintage_month_end"



def test_gdp_quarterly_vintage_end_is_safe_visibility_proxy():
    frame = pd.DataFrame({
        "Date": ["1990:Q2", "1990:Q3"],
        "ROUTPUT90Q3": [5000.0, None],
        "ROUTPUT90Q4": [5000.0, 5025.0],
        "ROUTPUT91Q1": [5000.0, 5025.0],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="DATA", index=False, startrow=2)

    rows = conservative_first_visible_dates(
        buf.getvalue(),
        source_url="https://example.test/routput-vintages.xlsx",
        frequency="quarterly",
    )

    q2 = rows["1990Q2"]
    q3 = rows["1990Q3"]
    assert q2["available_at"].startswith("1990-09-30T23:59:59")
    assert q3["available_at"].startswith("1990-12-31T23:59:59")
    assert q2["reaction_eligible"] is False
    assert q2["availability_precision"] == "conservative_vintage_quarter_end"



def test_livingston_release_date_parser_uses_release_column():
    frame = pd.DataFrame({
        "Survey Date": [
            pd.Timestamp("1990-06-01"),
            pd.Timestamp("1990-12-01"),
        ],
        "Release Date": [
            pd.Timestamp("1990-06-15"),
            pd.Timestamp("1990-12-20"),
        ],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Release Dates", index=False, startrow=2)

    rows = parse_livingston_release_dates(buf.getvalue())
    assert rows["1990-06"]["available_at"].startswith(
        "1990-06-15T23:59:59"
    )
    assert rows["1990-12"]["available_at"].startswith(
        "1990-12-20T23:59:59"
    )
    assert (
        rows["1990-06"]["availability_precision"]
        == "official_date_conservative_eod"
    )


def test_livingston_target_time_is_real_month_end():
    survey = pd.Timestamp("2025-06-01T23:59:59-04:00").to_pydatetime()
    target = target_time(survey, "12M")
    assert target.isoformat().startswith("2026-06-30T23:59:59")
