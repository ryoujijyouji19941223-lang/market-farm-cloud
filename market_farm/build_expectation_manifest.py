from __future__ import annotations

import json
from pathlib import Path

from .expectation_sources import source_manifest

OUT = Path("data/expectations/source_manifest.json")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(source_manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
