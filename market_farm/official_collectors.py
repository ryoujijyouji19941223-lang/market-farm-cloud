from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .official_archive import OfficialRecord, save_records


@dataclass(frozen=True)
class Collector:
    name: str
    authority: str
    collect: Callable[[], list[OfficialRecord]]


_COLLECTORS: dict[str, Collector] = {}


def register(collector: Collector) -> None:
    if collector.name in _COLLECTORS:
        raise ValueError(f"collector already registered: {collector.name}")
    _COLLECTORS[collector.name] = collector


def names() -> list[str]:
    return sorted(_COLLECTORS)


def run_collectors(selected: list[str] | None = None) -> dict:
    wanted = set(selected or names())
    report = {"collectors": {}, "saved": 0, "errors": 0}
    for name in names():
        if name not in wanted:
            continue
        collector = _COLLECTORS[name]
        try:
            records = collector.collect()
            saved = save_records(records)
            report["collectors"][name] = {"status": "ok", "records": len(records), "saved": saved}
            report["saved"] += saved
        except Exception as exc:
            report["collectors"][name] = {"status": "error", "error": str(exc)}
            report["errors"] += 1
    return report
