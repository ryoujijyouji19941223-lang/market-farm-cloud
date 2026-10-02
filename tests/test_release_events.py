from market_farm import build_release_events as module


def test_release_event_uses_latest_public_expectation_once(monkeypatch):
    expectations = [
        {
            "expectation_id": "old",
            "available_at": "2008-05-01T12:00:00-04:00",
            "expected_value": 2.0,
            "source": "SPF",
        },
        {
            "expectation_id": "latest",
            "available_at": "2008-08-01T12:00:00-04:00",
            "expected_value": 1.0,
            "source": "SPF",
        },
    ]
    actual = {
        "record_id": "a1",
        "event_key": "US_REAL_GDP_GROWTH:2008Q3",
        "indicator": "US_REAL_GDP_GROWTH",
        "observation_period": "2008Q3",
        "available_at": "2008-10-30T08:30:00-04:00",
        "value": -0.25,
        "unit": "percent",
        "source": "RTDSM",
    }
    pairs = {
        "items": [
            {
                "actual_record_id": "a1",
                "expectation_id": "old",
                "expectation_available_at": expectations[0]["available_at"],
                "status": "READY",
            },
            {
                "actual_record_id": "a1",
                "expectation_id": "latest",
                "expectation_available_at": expectations[1]["available_at"],
                "status": "READY",
            },
        ]
    }

    monkeypatch.setattr(module, "load_all_expectations", lambda: expectations)
    monkeypatch.setattr(module, "load_rows", lambda: [actual])
    monkeypatch.setattr(module, "load_reactions", lambda: [{
        "actual_record_id": "a1",
        "source_id": "us10y",
        "label": "US 10Y Treasury yield",
        "symbol": "DGS10",
        "unit": "percent",
        "provenance_url": "https://example.test/tnx",
        "data_provider": "yfinance_tnx_proxy",
        "fallback": True,
        "reaction": {"status": "OK"},
    }])
    monkeypatch.setattr(module, "build_pairs", lambda: pairs)

    rows = module.build_release_events()
    assert len(rows) == 1
    assert rows[0]["latest_public_expectation_id"] == "latest"
    assert rows[0]["eligible_expectation_count"] == 2
    assert rows[0]["surprise"] == -1.25
    assert rows[0]["causal_claim"] is None
    assert rows[0]["reactions"]["us10y"]["fallback"] is True
    assert rows[0]["reactions"]["us10y"]["data_provider"] == "yfinance_tnx_proxy"
