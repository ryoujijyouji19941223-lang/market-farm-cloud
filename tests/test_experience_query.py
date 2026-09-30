from datetime import datetime

from market_farm.experience_query import reaction_summary, similar_events


EVENTS = [
    {
        "actual_available_at": "2007-01-01T08:30:00-05:00",
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "weaker_growth",
        "surprise_direction": "BELOW",
        "reactions": {
            "sp500": {
                "status": "OK",
                "preferred_measure": "return",
                "horizons": {"1d": {"return": -0.01}},
            }
        },
    },
    {
        "actual_available_at": "2009-01-01T08:30:00-05:00",
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "weaker_growth",
        "surprise_direction": "BELOW",
        "reactions": {
            "sp500": {
                "status": "OK",
                "preferred_measure": "return",
                "horizons": {"1d": {"return": 0.05}},
            }
        },
    },
]


def test_analog_query_cannot_see_future_events():
    cutoff = datetime.fromisoformat("2008-01-01T12:00:00-05:00")
    rows = similar_events(
        cutoff=cutoff,
        indicator="US_REAL_GDP_GROWTH",
        semantic_effect="weaker_growth",
        events=EVENTS,
    )
    assert len(rows) == 1
    assert rows[0]["actual_available_at"].startswith("2007-")


def test_reaction_summary_uses_visible_events_only():
    cutoff = datetime.fromisoformat("2008-01-01T12:00:00-05:00")
    rows = similar_events(
        cutoff=cutoff,
        indicator="US_REAL_GDP_GROWTH",
        events=EVENTS,
    )
    summary = reaction_summary(rows, "sp500", "1d")
    assert summary["sample_count"] == 1
    assert summary["mean"] == -0.01
