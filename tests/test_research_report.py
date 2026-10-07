from market_farm.research_report import consensus_label, summarize_bucket


def row(prediction="UP", actual="UP", price=0.2, news=0.1, macro=0.05):
    return {
        "prediction": prediction,
        "actual": actual,
        "correct": prediction == actual,
        "price_score": price,
        "news_score": news,
        "macro_score": macro,
        "confidence": 0.1,
    }


def test_consensus_label_separates_agreement_and_conflict():
    assert consensus_label(row()) == "agree"
    assert consensus_label(row(price=0.2, news=-0.2, macro=0.0)) == "disagree"
    assert consensus_label(row(price=0.2, news=0.0, macro=0.0)) == "thin"


def test_summary_excludes_flat_predictions_from_signal_accuracy():
    rows = [
        row("UP", "UP"),
        row("DOWN", "UP"),
        row("FLAT", "FLAT"),
    ]
    s = summarize_bucket(rows)
    assert s["observations"] == 3
    assert s["signals"] == 2
    assert s["correct"] == 1
    assert s["accuracy"] == 0.5


def test_missing_news_is_not_factor_agreement():
    assert consensus_label(row(news=None)) == "thin"


def test_legacy_and_failed_news_rows_do_not_enter_current_comparisons(tmp_path, monkeypatch):
    import json
    from market_farm import research_report as module
    base = {"month": "2025-01", "assets": {"TEST": {"name": "Test", "news_error": "429", "snapshots": [
        {"prediction_direction": "UP", "prediction_probability_up": .7, "news_score": 0., "price_score": .5, "macro_score": .1,
         "horizons": {"next_day": {"direction": "UP"}}}
    ]}}}
    folder = tmp_path / "replay"
    folder.mkdir()
    (folder / "2025-01.json").write_text(json.dumps(base))
    monkeypatch.setattr(module, "REPLAY_DIR", folder)
    monkeypatch.setattr(module, "CARDS_DIR", tmp_path / "cards")
    monkeypatch.setattr(module, "OUT_JSON", tmp_path / "report.json")
    monkeypatch.setattr(module, "OUT_HTML", tmp_path / "report.html")
    out = module.build_report()
    assert out["replay_rows"] == 1
    assert out["eligible_replay_rows"] == 0
    assert out["by_asset"] == {}
    assert out["by_replay_version"]["legacy-date-only"]["news_status_counts"] == {"ERROR": 1}
