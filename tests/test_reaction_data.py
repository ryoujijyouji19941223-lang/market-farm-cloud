import pandas as pd
import pytest

from market_farm import reaction_data
from market_farm.reaction_sources import SOURCES


def test_dgs10_fallback_is_scaled_to_percent(monkeypatch):
    def fail_fred(*args, **kwargs):
        raise RuntimeError("fred down")

    idx = pd.date_range("2026-01-02", periods=2, freq="B")
    proxy = pd.DataFrame({"close": [5.0, 5.1]}, index=idx)

    monkeypatch.setattr(reaction_data, "_fred_frame", fail_fred)
    monkeypatch.setattr(
        reaction_data,
        "_yfinance_frame",
        lambda *args, **kwargs: proxy.copy(),
    )

    frame = reaction_data.fetch_reaction_frame(SOURCES["us10y"])
    assert frame.iloc[0]["close"] == pytest.approx(5.0)
    assert frame.iloc[1]["close"] == pytest.approx(5.1)
    assert frame.attrs["fallback"] is True
    assert frame.attrs["data_provider"] == "yfinance_tnx_proxy"


def test_usdjpy_fallback_keeps_quote_scale(monkeypatch):
    def fail_fred(*args, **kwargs):
        raise RuntimeError("fred down")

    idx = pd.date_range("2026-01-02", periods=1, freq="B")
    proxy = pd.DataFrame({"close": [150.0]}, index=idx)

    monkeypatch.setattr(reaction_data, "_fred_frame", fail_fred)
    monkeypatch.setattr(
        reaction_data,
        "_yfinance_frame",
        lambda *args, **kwargs: proxy.copy(),
    )

    frame = reaction_data.fetch_reaction_frame(SOURCES["usd_jpy"])
    assert frame.iloc[0]["close"] == 150.0
    assert frame.attrs["fallback"] is True
