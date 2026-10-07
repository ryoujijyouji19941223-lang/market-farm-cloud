from market_farm import refresh_dashboard as module


def test_refresh_uses_latest_persisted_run(monkeypatch):
    old = {"regime": {"risk_off": 1}, "results": [{"news_status": "UNKNOWN"}]}
    latest = {"regime": {"risk_off": 0}, "results": [{"news_status": "OK"}]}
    state = {"runs": [old, latest]}
    rendered = []
    monkeypatch.setattr(module, "load_state", lambda path: state)
    monkeypatch.setattr(module, "load_config", lambda: {})
    monkeypatch.setattr(module, "render", lambda cfg, regime, results, saved: rendered.append((regime, results, saved)))
    monkeypatch.setattr(module, "build_report", lambda: {"eligible_replay_rows": 3})
    assert module.refresh()["eligible_replay_rows"] == 3
    assert rendered == [(latest["regime"], latest["results"], state)]
