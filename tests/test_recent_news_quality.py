from datetime import datetime

import pandas as pd

from market_farm import recent_news_backtest as module


def test_news_ablation_uses_same_weights_and_excludes_failed_dates_from_both_arms(tmp_path, monkeypatch):
    assets = [{"symbol": "OK.T", "name": "OK", "kind": "equity"},
              {"symbol": "FAIL.T", "name": "FAIL", "kind": "equity"}]
    cfg = {"assets": assets, "market_proxies": {"sp500": "^GSPC"}, "recent_news_backtest_days": 35}
    idx = pd.bdate_range(end=datetime.now(module.JST).date(), periods=45)
    frame = pd.DataFrame({"close": 100., "price_score": .8, "macro": .1, "vol": .2,
                          "macro_status": "OK", "sp500_available_at": "2000-01-01T12:00:00+09:00"}, index=idx)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "load_config", lambda: cfg)
    monkeypatch.setattr(module, "fetch_history", lambda *args: None)
    monkeypatch.setattr(module, "feature_frame", lambda *args: pd.DataFrame())
    monkeypatch.setattr(module, "build_merged", lambda *args: frame)
    monkeypatch.setattr(module, "load_state", lambda *args: {})
    def fetch(query, *args):
        if query == "FAIL":
            raise RuntimeError("HTTP 429")
        return [], 0
    monkeypatch.setattr(module, "fetch_gdelt_range", fetch)
    out = module.run_recent_news_backtest()
    good = out["assets"]["OK.T"]
    bad = out["assets"]["FAIL.T"]
    assert good["rows"] and bad["rows"]
    assert all(r["baseline_probability_up"] == r["news_probability_up"] for r in good["rows"])
    assert bad["comparison_rows"] == 0
    assert bad["without_news"]["signals"] == bad["with_news"]["signals"] == 0
    assert all(r["news_score"] is None and r["news_correct"] is None for r in bad["rows"])
    assert out["overall"]["without_news"] == out["overall"]["with_news"]
