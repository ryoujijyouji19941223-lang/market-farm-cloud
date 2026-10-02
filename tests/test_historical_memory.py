import io

import pandas as pd

from market_farm.backfill_spf import _target_from_column
from market_farm.backfill_rtdsm import parse_first_releases, SOURCES
from market_farm.event_keys import event_key
from market_farm.spf_release_dates import parse_release_dates
from market_farm.bea_gdp_release_dates import parse_release_timestamp
from market_farm.bls_cpi_release_dates import parse_schedule


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
