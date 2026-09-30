from __future__ import annotations

import json
from pathlib import Path

STORE = Path("data/market_experience/reactions.jsonl")


def save_reactions(rows: list[dict]) -> int:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if STORE.exists():
        for line in STORE.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                existing[row["reaction_id"]] = row
            except Exception:
                continue
    for row in rows:
        existing[row["reaction_id"]] = row
    ordered = sorted(existing.values(), key=lambda x: (x["actual_available_at"], x["source_id"]))
    STORE.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in ordered) + ("\n" if ordered else ""),
        encoding="utf-8",
    )
    return len(rows)


def load_reactions() -> list[dict]:
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
