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
