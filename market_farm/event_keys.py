from __future__ import annotations

import re


def canonical_period(value: str) -> str:
    text = str(value).strip().upper().replace(":", "")
    q = re.fullmatch(r"(\d{4})[- ]?Q([1-4])", text)
    if q:
        return f"{q.group(1)}Q{q.group(2)}"
    m = re.fullmatch(r"(\d{4})[- ]?M(0?[1-9]|1[0-2])", text)
    if m:
        return f"{m.group(1)}M{int(m.group(2)):02d}"
    ym = re.fullmatch(r"(\d{4})[-/](0?[1-9]|1[0-2])", text)
    if ym:
        return f"{ym.group(1)}M{int(ym.group(2)):02d}"
    return text


def event_key(indicator: str, period: str) -> str:
    return f"{indicator}:{canonical_period(period)}"
