from market_farm.decision import forecast_qualification


def test_weak_evidence_abstains():
    result = forecast_qualification(0.51, 0.02, 0.01, 0.0)
    assert result["direction"] == "FLAT"
    assert result["decision"] == "ABSTAIN"


def test_strong_aligned_evidence_forecasts():
    result = forecast_qualification(0.68, 0.50, 0.30, 0.20)
    assert result["direction"] == "UP"
    assert result["decision"] == "FORECAST"


def test_flat_and_abstain_are_different_concepts():
    result = forecast_qualification(0.50, 0.30, -0.20, 0.10)
    assert result["direction"] == "FLAT"
    assert "decision" in result
