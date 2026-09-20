from __future__ import annotations
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from .engine import load_config, analyze, save_run
from .dashboard import render
from .ledger import create_live_cards, settle_live_cards
from .newspaper import render_newspaper
from .research_report import build_report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session", choices=["morning", "evening"])
    args = ap.parse_args()

    cfg = load_config()
    regime, results = analyze(cfg)

    # First close any older prediction cards using only a genuinely newer
    # market date. Then save the ordinary state and, on morning runs, freeze
    # a new auditable card before the future outcome is known.
    settle_live_cards(results)
    state = save_run(args.session, cfg, regime, results)

    if args.session == "morning":
        now = datetime.now(ZoneInfo(cfg["timezone"]))
        create_live_cards(cfg, regime, results, now=now)

    render(cfg, regime, results, state)
    render_newspaper(cfg, regime, results)
    build_report()

    for r in results:
        print(r["name"], r.get("action"), round(r.get("probability_up", .5) * 100, 1))


if __name__ == "__main__":
    main()
