from __future__ import annotations
from pathlib import Path
import json

DEFAULT = {"runs": [], "predictions": {}, "scores": {}, "paper": {"cash": 100000.0, "positions": {}, "history": []}}


def load_state(path="data/state.json"):
    p = Path(path)
    if not p.exists():
        return json.loads(json.dumps(DEFAULT))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for k, v in DEFAULT.items():
            data.setdefault(k, json.loads(json.dumps(v)))
        return data
    except Exception:
        return json.loads(json.dumps(DEFAULT))


def save_state(state, path="data/state.json"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
