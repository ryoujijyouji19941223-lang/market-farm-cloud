from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path("data/morning_brief.json")
STATE_PATH = Path("data/state.json")
CARDS_INDEX_PATH = Path("data/cards_index.json")
RESEARCH_PATH = Path("data/research_report.json")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _direction_label(direction: str) -> str:
    return {
        "UP": "上方向",
        "DOWN": "下方向",
        "FLAT": "方向感なし",
    }.get(direction, direction or "不明")


def _asset_row(result: dict) -> dict:
    qualification = result.get("forecast_qualification") or {}
    decision = qualification.get("decision")
    if decision is None:
        decision = "ABSTAIN" if result.get("action") == "NO_FORECAST" else "FORECAST"
    direction = qualification.get("direction")
    if direction is None:
        action = result.get("action")
        direction = action if action in {"UP", "DOWN", "FLAT"} else "FLAT"

    prob = result.get("probability_up")
    return {
        "symbol": result.get("symbol"),
        "name": result.get("name"),
        "kind": result.get("kind"),
        "price": result.get("price"),
        "market_date": result.get("market_date"),
        "day_change": result.get("day_change"),
        "direction_score": prob,
        "direction_meter": None if prob is None else round(float(prob) * 100),
        "direction": direction,
        "direction_label": _direction_label(direction),
        "decision": decision,
        "action": result.get("action"),
        "evidence_strength": qualification.get("evidence_strength"),
        "factor_agreement": qualification.get("factor_agreement"),
        "decision_reason": qualification.get("reason"),
        "price_score": result.get("price_score"),
        "news_score": result.get("news_score"),
        "news_status": result.get("news_status", "UNKNOWN"),
        "news_error": result.get("news_error"),
        "macro_score": result.get("macro_score"),
        "data_status": "OK" if result.get("price") is not None else "NO_DATA",
        "error": result.get("error"),
    }


def _market_date_summary(assets: list[dict]) -> dict:
    dates = sorted({
        str(x["market_date"])
        for x in assets
        if x.get("market_date")
    })
    return {
        "dates_present": dates,
        "earliest": dates[0] if dates else None,
        "latest": dates[-1] if dates else None,
        "single_market_date": dates[0] if len(dates) == 1 else None,
        "note": (
            "Each asset keeps its own market_date. Never describe generated_at "
            "as the price date."
        ),
    }


def _state_consistency(state: dict, assets: list[dict]) -> dict:
    runs = state.get("runs") or []
    latest = runs[-1] if runs else None
    if latest is None:
        return {
            "status": "NO_STATE_RUN",
            "latest_state_run_at_jst": None,
            "latest_state_session": None,
            "mismatches": [],
        }

    state_by_symbol = {
        row.get("symbol"): row
        for row in latest.get("results", [])
    }
    mismatches = []
    for asset in assets:
        previous = state_by_symbol.get(asset.get("symbol"))
        if previous is None:
            mismatches.append({
                "symbol": asset.get("symbol"),
                "name": asset.get("name"),
                "current_analysis_market_date": asset.get("market_date"),
                "state_market_date": None,
                "reason": "missing_from_latest_state_run",
            })
            continue
        if previous.get("market_date") != asset.get("market_date"):
            mismatches.append({
                "symbol": asset.get("symbol"),
                "name": asset.get("name"),
                "current_analysis_market_date": asset.get("market_date"),
                "state_market_date": previous.get("market_date"),
                "reason": "market_date_differs",
            })

    return {
        "status": "CONSISTENT" if not mismatches else "MIXED_TIMESTAMPS",
        "latest_state_run_at_jst": latest.get("timestamp"),
        "latest_state_session": latest.get("session"),
        "mismatches": mismatches,
        "authority_rule": (
            "Use current_analysis asset rows for the current snapshot. "
            "Use frozen prediction cards for historical predictions/outcomes. "
            "state.json is fallback/history, not authority over a newer analysis."
        ),
    }


def _card_payload(index_row: dict) -> dict:
    card_path = Path(index_row.get("path", ""))
    card = _load_json(card_path, {}) if str(card_path) else {}
    prediction = card.get("prediction") or {}
    outcome = card.get("outcome") or {}
    review = card.get("review") or {}

    score = prediction.get("direction_score", index_row.get("score"))
    return {
        "prediction_date": card.get("prediction_date", index_row.get("prediction_date")),
        "asset": card.get("name", index_row.get("name")),
        "symbol": card.get("symbol", index_row.get("symbol")),
        "decision": (
            prediction.get("qualification", {}).get("decision")
            or index_row.get("decision")
        ),
        "prediction": prediction.get("direction", index_row.get("direction")),
        "direction_meter": None if score is None else round(float(score) * 100),
        "market_data_through": card.get(
            "market_data_through",
            index_row.get("market_data_through"),
        ),
        "reference_price": card.get("reference_price"),
        "outcome_market_date": outcome.get("market_date"),
        "outcome_price": outcome.get("price"),
        "outcome_change": outcome.get("change"),
        "actual_direction": outcome.get("direction"),
        "correct": outcome.get("correct", index_row.get("correct")),
        "result_type": review.get("result_type", index_row.get("result_type")),
        "card_path": index_row.get("path"),
    }


def _learning_sentence(result_type: str | None, correct: bool | None) -> str | None:
    if result_type == "一致" or correct is True:
        return "方向は一致。次も同じ条件で再現するかを観察する。"
    if result_type == "方向を逆に読んだ":
        return "方向を逆に読んだ。価格・ニュース・外部環境のどれが逆向きだったかを次の検証材料にする。"
    if result_type == "動きを見逃した":
        return "横ばい寄りと読んだが動いた。弱い材料でも値動きが出る条件を検証する。"
    if result_type == "動くと読んだが横ばい":
        return "動くと読んだが横ばい。方向だけでなく値動きの強さを見直す。"
    return None


def _answer_check(cards_index: dict) -> dict:
    recent = [
        row for row in (cards_index.get("recent") or [])
        if row.get("prediction_date")
    ]
    forecast_rows = [row for row in recent if row.get("decision") == "FORECAST"]
    if not forecast_rows:
        return {
            "status": "NO_SCOREABLE_FORECAST",
            "headline": "まだ答え待ち",
            "reason": "recent cards contain no scoreable forecast",
            "card": None,
            "learning": None,
        }

    latest_date = max(row["prediction_date"] for row in forecast_rows)
    latest = [row for row in forecast_rows if row["prediction_date"] == latest_date]
    selected = max(
        latest,
        key=lambda row: abs(float(row.get("score", 0.5)) - 0.5),
    )
    payload = _card_payload(selected)

    if selected.get("status") != "SETTLED":
        return {
            "status": "WAITING",
            "headline": "まだ答え待ち",
            "reason": "the first traded market date after the frozen reference is not settled yet",
            "card": payload,
            "learning": None,
        }

    return {
        "status": "READY",
        "headline": "答え合わせ可能",
        "reason": None,
        "card": payload,
        "learning": _learning_sentence(
            payload.get("result_type"),
            payload.get("correct"),
        ),
    }


def build_morning_brief(
    cfg: dict,
    regime: dict,
    results: list[dict],
    *,
    state: dict | None = None,
    session: str = "newspaper",
    now: datetime | None = None,
    out: str | Path = OUT,
) -> dict:
    tz = ZoneInfo(cfg.get("timezone", "Asia/Tokyo"))
    now = now or datetime.now(tz)
    state = _load_json(STATE_PATH, {"runs": []}) if state is None else state
    cards_index = _load_json(CARDS_INDEX_PATH, {})
    research = _load_json(RESEARCH_PATH, {})

    assets = [_asset_row(row) for row in results]
    forecasted = [x for x in assets if x.get("decision") == "FORECAST"]
    abstained = [x for x in assets if x.get("decision") == "ABSTAIN"]
    focus = sorted(
        forecasted,
        key=lambda x: abs(float(x.get("direction_score") or 0.5) - 0.5),
        reverse=True,
    )[:3]

    source_state = _state_consistency(state, assets)
    answer_check = _answer_check(cards_index)

    brief = {
        "schema_version": 1,
        "brief_type": "market_farm_handoff",
        "generated_at_jst": now.isoformat(),
        "generated_by": session,
        "timezone": str(tz),
        "workflow_commit_sha": os.environ.get("GITHUB_SHA"),
        "date_semantics": {
            "brief_date": now.date().isoformat(),
            "brief_date_means": "handoff generation date, not a universal market price date",
            "market_dates": _market_date_summary(assets),
            "latest_state_run_at_jst": source_state.get("latest_state_run_at_jst"),
            "cards_index_updated_at": cards_index.get("updated_at"),
            "research_report_generated_at": research.get("generated_at"),
        },
        "snapshot_consistency": source_state,
        "current_analysis": {
            "regime": regime,
            "assets": assets,
            "forecast_count": len(forecasted),
            "abstain_count": len(abstained),
            "focus_forecasts": focus,
            "abstained": [
                {
                    "symbol": x.get("symbol"),
                    "name": x.get("name"),
                    "direction_meter": x.get("direction_meter"),
                    "reason": x.get("decision_reason"),
                }
                for x in abstained
            ],
        },
        "answer_check": answer_check,
        "research_status": {
            "generated_at": research.get("generated_at"),
            "replay_month_count": research.get("replay_month_count"),
            "replay_rows": research.get("replay_rows"),
            "live_settled_rows": research.get("live_settled_rows"),
            "note": research.get("note"),
        },
        "fresh_external_inputs": {
            "important_events_48h": {
                "status": "REQUIRES_FRESH_WEB",
                "items": [],
                "instruction": (
                    "Fetch current official/high-quality calendar sources at newspaper time. "
                    "Do not infer future events from stale repository data."
                ),
            },
            "latest_news": {
                "status": "REQUIRES_FRESH_WEB",
                "items": [],
                "instruction": (
                    "Use current web/news sources for today's macro and company news. "
                    "Treat news as material candidates, not proven causes."
                ),
            },
        },
        "consumer_contract": {
            "primary_source": "data/morning_brief.json",
            "fallback_sources": [
                "data/state.json",
                "data/cards_index.json and referenced card files",
                "data/research_report.json",
                "docs/newspaper.html",
            ],
            "rules": [
                "Read this file before composing the human morning newspaper.",
                "If GitHub Pages is unavailable but repository files are readable, do not say Market Farm is unavailable.",
                "Keep brief generation date, state run timestamp, prediction date, and each asset market_date separate.",
                "Use current_analysis for the current snapshot; use frozen cards for prediction-time evidence and scoring.",
                "Fetch fresh web data for the next 48 hours of events and current news.",
                "If a fact or source cannot be verified, label it unverified rather than filling the gap.",
                "Do not claim a headline caused a price move; say material candidate or possible relation.",
                "Show exactly one answer_check item; if not settled, say まだ答え待ち.",
            ],
        },
        "unverified_or_external": [
            "today_to_48h_important_events",
            "fresh_macro_news",
            "fresh_company_news",
        ],
    }

    canonical = json.dumps(
        brief,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    brief["snapshot_id"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return brief


def main():
    from .engine import analyze, load_config

    cfg = load_config()
    regime, results = analyze(cfg)
    payload = build_morning_brief(
        cfg,
        regime,
        results,
        session="manual",
    )
    print(json.dumps({
        "snapshot_id": payload["snapshot_id"],
        "generated_at_jst": payload["generated_at_jst"],
        "forecast_count": payload["current_analysis"]["forecast_count"],
        "abstain_count": payload["current_analysis"]["abstain_count"],
        "answer_check": payload["answer_check"]["status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
