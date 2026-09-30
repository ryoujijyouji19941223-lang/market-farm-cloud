from __future__ import annotations

from datetime import datetime
import pandas as pd


HORIZONS = {
    "1d": 1,
    "2d": 2,
    "5d": 5,
    "20d": 20,
}


def reaction_from_frame(frame: pd.DataFrame, released_at: str) -> dict:
    release = datetime.fromisoformat(released_at)
    if release.tzinfo is None:
        raise ValueError("released_at must be timezone-aware")
    if frame.empty or "close" not in frame.columns:
        return {"status": "MISSING_MARKET_DATA"}

    idx = pd.DatetimeIndex(frame.index)
    release_ts = pd.Timestamp(release)
    if idx.tz is None:
        release_ts = release_ts.tz_localize(None)
    else:
        release_ts = release_ts.tz_convert(idx.tz)

    positions = [i for i, value in enumerate(idx) if value >= release_ts]
    if not positions:
        return {"status": "NO_POST_RELEASE_OBSERVATION"}

    base_pos = positions[0]
    base = float(frame.iloc[base_pos]["close"])
    out = {
        "status": "OK",
        "base_time": pd.Timestamp(idx[base_pos]).isoformat(),
        "base_close": base,
        "horizons": {},
    }
    for name, steps in HORIZONS.items():
        pos = base_pos + steps
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
