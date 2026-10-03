from market_farm.backfill_reactions import _needs_refresh


def test_missing_reaction_needs_refresh():
    assert _needs_refresh(None) is True


def test_transient_source_failure_needs_refresh():
    row = {
        "data_provider": "yfinance",
        "reaction": {"status": "SOURCE_FETCH_ERROR"},
    }
    assert _needs_refresh(row) is True


def test_genuine_market_gap_is_cached():
    row = {
        "data_provider": "yfinance",
        "reaction": {"status": "MISSING_MARKET_WINDOW"},
    }
    assert _needs_refresh(row) is False


def test_successful_reaction_is_cached():
    row = {
        "data_provider": "yfinance",
        "reaction": {"status": "OK"},
    }
    assert _needs_refresh(row) is False


def test_old_row_without_provider_refreshes_once():
    row = {
        "reaction": {"status": "OK"},
    }
    assert _needs_refresh(row) is True
