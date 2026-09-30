from __future__ import annotations

import json
from pathlib import Path

STORE = Path("data/actual_releases")


def save_rows(dataset: str, rows: list[dict]) -> int:
    path = STORE / f"{dataset}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                existing[row["record_id"]] = row
            except Exception:
                continue
    for row in rows:
        existing[row["record_id"]] = row
    ordered = sorted(
        existing.values(),
        key=lambda x: (x.get("observation_period", ""), x.get("release_number", 0), x["record_id"]),
    )
    path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in ordered) + ("\n" if ordered else ""),
        encoding="utf-8",
    )
    return len(rows)


def load_rows(dataset: str | None = None) -> list[dict]:
    out = []
    paths = [STORE / f"{dataset}.jsonl"] if dataset else sorted(STORE.glob("*.jsonl"))
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def pairable(row: dict) -> bool:
    return bool(row.get("event_key")) and row.get("release_number") == 1
