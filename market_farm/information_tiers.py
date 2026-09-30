from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InformationTier:
    tier: str
    usable_for_live_replay: bool
    description: str


PUBLIC_REALTIME = InformationTier(
    "public_realtime", True,
    "Information demonstrably public by the historical cutoff."
)
DELAYED_RESEARCH = InformationTier(
    "delayed_research", False,
    "Information created historically but released to the public only later."
)
REVISED_HINDSIGHT = InformationTier(
    "revised_hindsight", False,
    "Later revised/final data; evaluation only, never historical prediction input."
)


def assert_prediction_visible(record: dict, cutoff: datetime) -> None:
    if record.get("information_tier") != PUBLIC_REALTIME.tier:
        raise ValueError("record is not eligible for historical prediction input")
    available = datetime.fromisoformat(record["available_at"])
    if available.tzinfo is None or cutoff.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    if available > cutoff:
        raise ValueError("record became public after prediction cutoff")
