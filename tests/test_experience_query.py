from datetime import datetime

from market_farm.experience_query import (
    analog_report_for_release_event,
    reaction_summary,
    similar_events,
)


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
    summary = reaction_summary(rows, "sp500", "1d", min_samples=1)
    assert summary["sample_count"] == 1
    assert summary["status"] == "OK"
    assert summary["mean"] == -0.01



def test_regime_filter_excludes_different_environment():
    events = [
        {
            **EVENTS[0],
            "pre_release_context": {
                "regime_signature": {
                    "quality": "FULL",
                    "headline_level": "high",
                    "headline_momentum": "heating",
                }
            },
        },
        {
            **EVENTS[1],
            "actual_available_at": "2007-06-01T08:30:00-04:00",
            "pre_release_context": {
                "regime_signature": {
                    "quality": "FULL",
                    "headline_level": "low",
                    "headline_momentum": "cooling",
                }
            },
        },
    ]
    cutoff = datetime.fromisoformat("2008-01-01T12:00:00-05:00")
    rows = similar_events(
        cutoff=cutoff,
        indicator="US_REAL_GDP_GROWTH",
        semantic_effect="weaker_growth",
        regime_filters={
            "headline_level": "high",
            "headline_momentum": "heating",
        },
        events=events,
    )
    assert len(rows) == 1
    assert rows[0]["pre_release_context"]["regime_signature"]["headline_level"] == "high"


def test_small_analog_sample_is_suppressed():
    summary = reaction_summary(EVENTS[:1], "sp500", "1d", min_samples=5)
    assert summary["sample_count"] == 1
    assert summary["status"] == "INSUFFICIENT_SAMPLE"
    assert summary["mean"] is None
    assert summary["median"] is None



def test_release_event_analog_report_cannot_use_itself_or_future():
    base = {
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "stronger_growth",
        "surprise_direction": "ABOVE",
        "pre_release_context": {
            "regime_signature": {
                "headline_level": "high",
                "headline_momentum": "heating",
            }
        },
        "reactions": {
            "sp500": {
                "status": "OK",
                "preferred_measure": "return",
                "data_provider": "yfinance",
                "fallback": False,
                "horizons": {"1d": {"return": 0.01}},
            }
        },
    }
    past = {
        **base,
        "release_event_id": "past",
        "actual_available_at": "2007-01-01T08:30:00-05:00",
    }
    current = {
        **base,
        "release_event_id": "current",
        "actual_available_at": "2008-01-01T08:30:00-05:00",
    }
    future = {
        **base,
        "release_event_id": "future",
        "actual_available_at": "2009-01-01T08:30:00-05:00",
    }

    report = analog_report_for_release_event(
        current,
        events=[past, current, future],
        min_samples=1,
    )
    assert report["status"] == "OK"
    assert report["event_count"] == 1
    assert report["markets"]["sp500"]["1d"]["sample_count"] == 1


def test_release_event_analog_report_marks_missing_regime_and_falls_back():
    past = {
        "release_event_id": "past",
        "actual_available_at": "2007-01-01T08:30:00-05:00",
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "stronger_growth",
        "surprise_direction": "ABOVE",
        "pre_release_context": {"regime_signature": {"quality": "MISSING"}},
        "reactions": {},
    }
    event = {
        "release_event_id": "x",
        "actual_available_at": "2008-01-01T08:30:00-05:00",
        "indicator": "US_REAL_GDP_GROWTH",
        "semantic_effect": "stronger_growth",
        "surprise_direction": "ABOVE",
        "pre_release_context": {"regime_signature": {"quality": "MISSING"}},
    }
    report = analog_report_for_release_event(
        event, events=[past, event], min_samples=1
    )
    assert report["status"] == "OK"
    assert report["similarity_tier"] == "SURPRISE_ONLY"
    assert report["regime_context_missing"] is True
    assert report["event_count"] == 1



def test_release_event_analog_report_relaxes_regime_hierarchy():
    def ev(event_id, when, level, momentum):
        return {
            "release_event_id": event_id,
            "actual_available_at": when,
            "indicator": "US_REAL_GDP_GROWTH",
            "semantic_effect": "weaker_growth",
            "surprise_direction": "BELOW",
            "pre_release_context": {
                "regime_signature": {
                    "headline_level": level,
                    "headline_momentum": momentum,
                }
            },
            "reactions": {},
        }

    past = [
        ev("a", "2001-01-01T08:30:00-05:00", "high", "cooling"),
        ev("b", "2002-01-01T08:30:00-05:00", "high", "mixed"),
        ev("c", "2003-01-01T08:30:00-05:00", "high", "heating"),
    ]
    current = ev(
        "current", "2004-01-01T08:30:00-05:00", "high", "heating"
    )
    report = analog_report_for_release_event(
        current,
        events=[*past, current],
        min_samples=2,
    )
    assert report["status"] == "OK"
    assert report["similarity_tier"] == "LEVEL_ONLY"
    assert report["event_count"] == 3
    assert report["search_attempts"][0]["similarity_tier"] == "LEVEL_AND_MOMENTUM"
    assert report["search_attempts"][0]["event_count"] == 1
