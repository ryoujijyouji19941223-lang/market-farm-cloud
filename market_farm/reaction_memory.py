from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd


HORIZONS = {
    "1d": 0,
    "2d": 1,
    "5d": 4,
    "20d": 19,
}


def reaction_from_frame(
    frame: pd.DataFrame,
    released_at: str,
    *,
    market_timezone: str = "America/New_York",
    close_hour: int = 16,
    close_minute: int = 0,
) -> dict:
    """Measure daily-close reaction from the last close knowable before release.

    Daily price indexes are treated as trading-session labels, not literal
    midnight observation timestamps. If a release arrives before that market's
    close, that same session's close is the first reaction close. If it arrives
    after close, the next trading session is used.
    """
    release = datetime.fromisoformat(released_at)
    if release.tzinfo is None:
        raise ValueError("released_at must be timezone-aware")
    if frame.empty or "close" not in frame.columns:
        return {"status": "MISSING_MARKET_DATA"}

    idx = pd.DatetimeIndex(frame.index)
    market_tz = ZoneInfo(market_timezone)
    local_release = release.astimezone(market_tz)
    release_date = local_release.date()
    close_clock = time(close_hour, close_minute)
    same_session_eligible = local_release.time().replace(tzinfo=None) <= close_clock

    session_dates = [pd.Timestamp(x).date() for x in idx]
    reaction_positions = [
        i for i, day in enumerate(session_dates)
        if day > release_date or (same_session_eligible and day == release_date)
    ]
    if not reaction_positions:
        return {"status": "NO_POST_RELEASE_OBSERVATION"}

    reaction_pos = reaction_positions[0]
    if reaction_pos == 0:
        return {"status": "NO_PRE_RELEASE_BASELINE"}

    base_pos = reaction_pos - 1
    base = float(frame.iloc[base_pos]["close"])
    out = {
        "status": "OK",
        "released_at": release.isoformat(),
        "market_timezone": market_timezone,
        "market_close": f"{close_hour:02d}:{close_minute:02d}",
        "base_time": pd.Timestamp(idx[base_pos]).isoformat(),
        "base_close": base,
        "first_reaction_time": pd.Timestamp(idx[reaction_pos]).isoformat(),
        "horizons": {},
    }
    for name, offset in HORIZONS.items():
        pos = reaction_pos + offset
        if pos >= len(frame):
            out["horizons"][name] = None
            continue
        close = float(frame.iloc[pos]["close"])
        out["horizons"][name] = {
            "time": pd.Timestamp(idx[pos]).isoformat(),
            "close": close,
            "return": close / base - 1.0,
        }
    return out
