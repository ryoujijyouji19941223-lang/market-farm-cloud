from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .actual_archive import load_rows
from .build_experience_pairs import build_pairs
from .expectation_memory import load_all_expectations
from .experience_builder import assemble_experience
from .market_experience import save_experiences
from .reaction_archive import load_reactions

STATUS = Path("data/market_experience/build_status.json")


def main():
    expectations = {x["expectation_id"]: x for x in load_all_expectations()}
    actuals = {x["record_id"]: x for x in load_rows()}
    reaction_map = defaultdict(dict)

    for row in load_reactions():
        reaction_map[row["actual_record_id"]][row["source_id"]] = {
            "label": row.get("label"),
            "symbol": row.get("symbol"),
            "unit": row.get("unit"),
            "provenance_url": row.get("provenance_url"),
            "data_provider": row.get("data_provider"),
            "fallback": bool(row.get("fallback", False)),
            **row.get("reaction", {}),
        }

    pair_payload = build_pairs()
    experiences = []
    skipped = []
    allowed = {"READY", "READY_SURPRISE_ONLY"}

    for pair in pair_payload["items"]:
        if pair["status"] not in allowed:
            skipped.append({"pair": pair, "reason": pair["status"]})
            continue
        expectation = expectations.get(pair["expectation_id"])
        actual = actuals.get(pair["actual_record_id"])
        if expectation is None or actual is None:
            skipped.append({"pair": pair, "reason": "missing_source_record"})
            continue
        try:
            reactions = reaction_map.get(actual["record_id"], {}) if pair["status"] == "READY" else {}
            experience = assemble_experience(
                expectation=expectation,
                actual=actual,
                reactions=reactions,
                information_cutoff=actual["available_at"],
            )
            experiences.append(experience)
        except Exception as exc:
            skipped.append({"pair": pair, "reason": str(exc)})

    saved = save_experiences(experiences)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pair_status_counts": pair_payload["status_counts"],
        "pairs": pair_payload["pairs"],
        "experiences": len(experiences),
        "saved": saved,
        "skipped_count": len(skipped),
        "skipped_examples": skipped[:10],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"market experiences={len(experiences)} saved={saved} skipped={len(skipped)}")


if __name__ == "__main__":
    main()
