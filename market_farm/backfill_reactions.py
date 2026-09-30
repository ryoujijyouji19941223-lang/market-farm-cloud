from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .actual_archive import load_rows
from .reaction_archive import save_reactions
from .reaction_data import fetch_reaction_frame
from .reaction_memory import reaction_from_frame
from .reaction_sources import SOURCES

STATUS = Path("data/market_experience/reaction_backfill_status.json")


def _reaction_id(actual_record_id: str, source_id: str) -> str:
    raw = f"{actual_record_id}|{source_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _decorate_measurement(source, reaction: dict) -> dict:
    if reaction.get("status") != "OK":
        return reaction
    if source.unit == "percent":
        base = float(reaction["base_close"])
        for row in reaction["horizons"].values():
            if row is None:
                continue
            row["change_bps"] = (float(row["close"]) - base) * 100.0
        reaction["preferred_measure"] = "change_bps"
    else:
        reaction["preferred_measure"] = "return"
    return reaction


def main():
    actuals = [
        row for row in load_rows()
        if row.get("release_number") == 1 and row.get("information_tier") == "public_realtime"
    ]
    if not actuals:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "no_actual_releases",
            "sources": {},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("No first-release actuals available for reaction backfill.")
        return

    releases = [datetime.fromisoformat(x["available_at"]) for x in actuals]
    start = min(releases) - timedelta(days=10)
    end = max(releases) + timedelta(days=45)

    frames = {}
    source_status = {}
    for source_id, source in SOURCES.items():
        try:
            frame = fetch_reaction_frame(source, start, end)
            frames[source_id] = frame
            source_status[source_id] = {
                "status": "ok" if not frame.empty else "complete_empty",
                "rows": int(len(frame)),
                "first_date": None if frame.empty else str(frame.index.min()),
                "last_date": None if frame.empty else str(frame.index.max()),
            }
        except Exception as exc:
            frames[source_id] = None
            source_status[source_id] = {"status": "fetch_error", "error": str(exc)}

    out = []
    for actual in actuals:
        for source_id, source in SOURCES.items():
            frame = frames.get(source_id)
            if frame is None:
                reaction = {"status": "SOURCE_FETCH_ERROR"}
            else:
                reaction = reaction_from_frame(
                    frame,
                    actual["available_at"],
                    market_timezone=source.timezone,
                    close_hour=source.close_hour,
                    close_minute=source.close_minute,
                )
                reaction = _decorate_measurement(source, reaction)

            out.append({
                "reaction_id": _reaction_id(actual["record_id"], source_id),
                "actual_record_id": actual["record_id"],
                "event_key": actual["event_key"],
                "actual_available_at": actual["available_at"],
                "source_id": source_id,
                "label": source.label,
                "symbol": source.symbol,
                "unit": source.unit,
                "information_tier": "post_event_evaluation",
                "provenance_url": source.provenance_url,
                "reaction": reaction,
            })

    saved = save_reactions(out)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "actual_release_count": len(actuals),
        "reaction_rows": len(out),
        "saved": saved,
        "sources": source_status,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"reaction rows={len(out)} saved={saved}")


if __name__ == "__main__":
    main()
