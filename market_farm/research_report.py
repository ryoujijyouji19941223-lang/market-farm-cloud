from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

REPLAY_DIR = Path("data/replay")
CARDS_DIR = Path("data/cards")
OUT_JSON = Path("data/research_report.json")
OUT_HTML = Path("docs/research.html")


def factor_direction(value, threshold=0.04):
    if value is None:
        return "NEUTRAL"
    if value >= threshold:
        return "UP"
    if value <= -threshold:
        return "DOWN"
    return "NEUTRAL"


def accuracy(rows):
    if not rows:
        return None
    return sum(bool(r["correct"]) for r in rows) / len(rows)


def summarize_bucket(rows):
    signals = [r for r in rows if r["prediction"] != "FLAT"]
    return {
        "observations": len(rows),
        "signals": len(signals),
        "coverage": (len(signals) / len(rows)) if rows else None,
        "correct": sum(bool(r["correct"]) for r in signals),
        "accuracy": accuracy(signals),
    }


def consensus_label(row):
    dirs = [
        factor_direction(row.get("price_score")),
        factor_direction(row.get("news_score")),
        factor_direction(row.get("macro_score")),
    ]
    active = [d for d in dirs if d != "NEUTRAL"]
    if len(active) >= 2 and len(set(active)) == 1:
        return "agree"
    if len(active) >= 2 and len(set(active)) > 1:
        return "disagree"
    return "thin"


def replay_rows():
    rows = []
    if not REPLAY_DIR.exists():
        return rows

    for path in sorted(REPLAY_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        month = data.get("month")
        for symbol, asset in data.get("assets", {}).items():
            for snap in asset.get("snapshots", []):
                prediction = snap.get("prediction_direction")
                prob = snap.get("prediction_probability_up")
                if prediction is None:
                    continue
                for horizon, outcome in (snap.get("horizons") or {}).items():
                    if not outcome or outcome.get("direction") is None:
                        continue
                    rows.append({
                        "source": "replay",
                        "month": month,
                        "symbol": symbol,
                        "name": asset.get("name", symbol),
                        "horizon": horizon,
                        "prediction": prediction,
                        "actual": outcome.get("direction"),
                        "correct": prediction == outcome.get("direction"),
                        "probability_up": prob,
                        "confidence": abs(float(prob) - 0.5) if prob is not None else 0.0,
                        "price_score": snap.get("price_score"),
                        "news_score": snap.get("news_score"),
                        "macro_score": snap.get("macro_score"),
                    })
    return rows


def live_rows():
    rows = []
    if not CARDS_DIR.exists():
        return rows
    for path in sorted(CARDS_DIR.glob("*/*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if card.get("status") != "SETTLED" or not card.get("outcome"):
            continue
        evidence = card.get("evidence", {})
        rows.append({
            "source": "live",
            "symbol": card.get("symbol"),
            "name": card.get("name"),
            "horizon": "next_day",
            "prediction": card.get("prediction", {}).get("direction"),
            "actual": card.get("outcome", {}).get("direction"),
            "correct": bool(card.get("outcome", {}).get("correct")),
            "probability_up": card.get("prediction", {}).get("direction_score"),
            "confidence": abs(float(card.get("prediction", {}).get("direction_score", 0.5)) - 0.5),
            "price_score": evidence.get("price", {}).get("score"),
            "news_score": evidence.get("news", {}).get("score"),
            "macro_score": evidence.get("outside_wind", {}).get("score"),
            "result_type": card.get("review", {}).get("result_type"),
        })
    return rows


def compare_slice(rows, predicate):
    a = [r for r in rows if predicate(r)]
    return summarize_bucket(a)


def build_report():
    replay = replay_rows()
    live = live_rows()
    months = sorted({r.get("month") for r in replay if r.get("month")})

    by_asset = {}
    keys = sorted({(r["symbol"], r["name"]) for r in replay})
    for symbol, name in keys:
        asset_rows = [r for r in replay if r["symbol"] == symbol]
        horizons = {}
        for horizon in ("next_day", "two_days", "one_month"):
            h = [r for r in asset_rows if r["horizon"] == horizon]
            if not h:
                continue
            horizons[horizon] = {
                "overall": summarize_bucket(h),
                "factor_agreement": compare_slice(h, lambda r: consensus_label(r) == "agree"),
                "factor_disagreement": compare_slice(h, lambda r: consensus_label(r) == "disagree"),
                "strong_calls": compare_slice(h, lambda r: r["confidence"] >= 0.12),
                "mild_calls": compare_slice(h, lambda r: 0.05 <= r["confidence"] < 0.12),
            }
        by_asset[symbol] = {"name": name, "horizons": horizons}

    live_by_asset = {}
    for symbol, name in sorted({(r["symbol"], r["name"]) for r in live}):
        rs = [r for r in live if r["symbol"] == symbol]
        live_by_asset[symbol] = {
            "name": name,
            "summary": summarize_bucket(rs),
            "result_types": dict(Counter(r.get("result_type") or "不明" for r in rs)),
        }

    hypotheses = []
    for symbol, asset in by_asset.items():
        for horizon, stats in asset["horizons"].items():
            agree = stats["factor_agreement"]
            disagree = stats["factor_disagreement"]
            strong = stats["strong_calls"]
            mild = stats["mild_calls"]

            if (
                agree.get("signals", 0) >= 20
                and disagree.get("signals", 0) >= 20
                and agree.get("accuracy") is not None
                and disagree.get("accuracy") is not None
                and agree["accuracy"] >= disagree["accuracy"] + 0.08
            ):
                hypotheses.append({
                    "symbol": symbol,
                    "name": asset["name"],
                    "horizon": horizon,
                    "type": "agreement",
                    "text": "価格・ニュース・外部環境が同じ方向を向く時だけ使う案を検証する価値あり",
                    "evidence": {
                        "agree_accuracy": agree["accuracy"],
                        "agree_signals": agree["signals"],
                        "disagree_accuracy": disagree["accuracy"],
                        "disagree_signals": disagree["signals"],
                    },
                })

            if (
                strong.get("signals", 0) >= 20
                and mild.get("signals", 0) >= 20
                and strong.get("accuracy") is not None
                and mild.get("accuracy") is not None
                and strong["accuracy"] + 0.08 <= mild["accuracy"]
            ):
                hypotheses.append({
                    "symbol": symbol,
                    "name": asset["name"],
                    "horizon": horizon,
                    "type": "confidence_warning",
                    "text": "強い向きメーターがむしろ弱い可能性。スコアの自信度を再設計する候補",
                    "evidence": {
                        "strong_accuracy": strong["accuracy"],
                        "strong_signals": strong["signals"],
                        "mild_accuracy": mild["accuracy"],
                        "mild_signals": mild["signals"],
                    },
                })

    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "replay_months": months,
        "replay_month_count": len(months),
        "replay_rows": len(replay),
        "live_settled_rows": len(live),
        "note": "Diagnostics only. These findings must not auto-change the production model.",
        "by_asset": by_asset,
        "live_by_asset": live_by_asset,
        "hypotheses": hypotheses,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    render_html(report)
    return report


def pct_or_dash(v):
    return "-" if v is None else f"{v*100:.0f}%"


def render_html(report):
    rows = []
    for symbol, asset in report.get("by_asset", {}).items():
        h = asset.get("horizons", {}).get("next_day", {})
        overall = h.get("overall", {})
        agree = h.get("factor_agreement", {})
        disagree = h.get("factor_disagreement", {})
        rows.append(
            f"<tr><td>{escape(asset['name'])}</td>"
            f"<td>{pct_or_dash(overall.get('accuracy'))} / {overall.get('signals',0)}回</td>"
            f"<td>{pct_or_dash(agree.get('accuracy'))} / {agree.get('signals',0)}回</td>"
            f"<td>{pct_or_dash(disagree.get('accuracy'))} / {disagree.get('signals',0)}回</td></tr>"
        )

    hypotheses = []
    for h in report.get("hypotheses", [])[:12]:
        label = {"next_day":"翌日","two_days":"2日後","one_month":"約1か月後"}.get(h.get("horizon"), h.get("horizon"))
        hypotheses.append(
            f"<div class='hyp'><b>{escape(h.get('name',''))}・{escape(str(label))}</b>"
            f"<p>{escape(h.get('text',''))}</p>"
            f"<small>これは改良候補。まだ本番モデルへ自動採用しません。</small></div>"
        )

    html = f"""<!doctype html>
<html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>市場農場 研究レポート</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f6;color:#171717;font-family:system-ui,-apple-system,"Yu Gothic",sans-serif;line-height:1.7}}
main{{max-width:950px;margin:auto;padding:14px}}section{{background:white;border:1px solid #ddd;border-radius:14px;padding:18px;margin:14px 0}}
h1,h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}.grid div,.hyp{{background:#f6f7f8;border-radius:10px;padding:12px}}small{{color:#666}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<section><h1>市場農場 研究レポート</h1>
<p>「どんな時に当たり、どんな時に外すか」を自動で探すページです。<b>ここで見つけた傾向は、まだ予測器へ自動採用しません。</b></p>
<div class='grid'>
<div><small>歴史再現</small><br><b>{report.get('replay_month_count',0)}か月</b></div>
<div><small>歴史再現の判定行</small><br><b>{report.get('replay_rows',0)}</b></div>
<div><small>本番で答え合わせ済み</small><br><b>{report.get('live_settled_rows',0)}</b></div>
</div>
<p><a href='./index.html'>研究用市場農場</a> ｜ <a href='./newspaper.html'>朝刊</a></p></section>

<section><h2>翌日予測は、どんな時にマシ？</h2>
<p>「3つ一致」は価格・ニュース・外部環境のうち、少なくとも2つの有効な方向が同じ時。「不一致」は有効な方向がぶつかっている時です。</p>
<div style='overflow:auto'><table><thead><tr><th>対象</th><th>全体</th><th>3要素が一致気味</th><th>要素が不一致</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>

<section><h2>次に調べる候補</h2>
{''.join(hypotheses) if hypotheses else "<p>まだ十分な回数がないか、強い差は見つかっていません。データを増やします。</p>"}
</section>
</main></body></html>"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")


def main():
    report = build_report()
    print("research report", report["replay_month_count"], "months", len(report["hypotheses"]), "hypotheses")


if __name__ == "__main__":
    main()
