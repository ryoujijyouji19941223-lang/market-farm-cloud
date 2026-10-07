"""Rebuild shared views from the latest persisted data after parallel jobs."""
from .dashboard import render
from .engine import load_config
from .research_report import build_report
from .state import load_state


def refresh():
    state = load_state("data/state.json")
    if not state.get("runs"):
        raise RuntimeError("No persisted market run is available for the dashboard")
    latest = state["runs"][-1]
    render(load_config(), latest["regime"], latest["results"], state)
    return build_report()


if __name__ == "__main__":
    report = refresh()
    print("Dashboard refreshed", report["replay_month_count"], "months", report["eligible_replay_rows"], "eligible rows")
