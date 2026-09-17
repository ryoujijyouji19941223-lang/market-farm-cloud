from __future__ import annotations
from pathlib import Path
from datetime import datetime
from html import escape


def pct(x):
    try: return f"{x*100:+.2f}%"
    except: return "-"


def render(cfg, regime, results, state, out="docs/index.html"):
    rows=[]
    for r in results:
        if r.get("price") is None:
            rows.append(f"<tr><td>{escape(r['name'])}</td><td colspan='6'>取得失敗</td></tr>")
            continue
        sc=state.get("scores",{}).get(r["symbol"],{})
        acc = "-" if not sc.get("total") else f"{100*sc['correct']/sc['total']:.0f}% ({sc['correct']}/{sc['total']})"
        rows.append(f"<tr><td>{escape(r['name'])}</td><td>{r['price']:.3f}</td><td>{pct(r['day_change'])}</td><td>{pct(r['momentum5'])}</td><td>{r['probability_up']*100:.0f}%</td><td>{escape(r['action'])}</td><td>{acc}</td></tr>")
    latest = state.get("runs", [])[-1] if state.get("runs") else {}
    timestamp = latest.get("timestamp", datetime.now().astimezone().isoformat())
    reg = regime
    body=f"""<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>市場農場</title>
<style>body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f5f5;color:#171717}}main{{max-width:1100px;margin:auto;padding:20px}}.card{{background:white;border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 1px 5px #0001}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #ddd;text-align:right}}th:first-child,td:first-child{{text-align:left}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}.metric{{font-size:1.5rem;font-weight:700}}small{{color:#666}}@media(max-width:700px){{table{{font-size:12px}}th,td{{padding:7px 4px}}}}</style></head><body><main>
<h1>市場農場</h1><p>最終更新: {escape(timestamp)}</p>
<div class='card'><h2>世界の空模様</h2><div class='grid'>
<div><small>リスク回避</small><div class='metric'>{reg['risk_off']:+.2f}</div></div>
<div><small>原油圧力</small><div class='metric'>{reg['oil_pressure']:+.2f}</div></div>
<div><small>ドル金利圧力</small><div class='metric'>{reg['usd_rate_pressure']:+.2f}</div></div>
<div><small>日本株ストレス</small><div class='metric'>{reg['japan_risk']:+.2f}</div></div>
</div></div>
<div class='card'><h2>今日の作物</h2><div style='overflow:auto'><table><thead><tr><th>対象</th><th>価格</th><th>前日比</th><th>5日</th><th>上昇スコア</th><th>判定</th><th>過去精度</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>
<div class='card'><h2>読み方</h2><p><b>BUY_CANDIDATE</b> は仮想検証上の上向き候補、<b>RISK_OFF</b> は下向き警戒、<b>HOLD</b> は方向感が弱い状態です。</p><p>「上昇スコア」はまだ校正済み確率ではありません。朝の予測と次回価格を蓄積し、精度を実測していきます。</p></div>
<div class='card'><small>投資助言ではなく学習・仮想検証用。価格データやニュース取得元の障害で値が欠けることがあります。</small></div>
</main></body></html>"""
    p=Path(out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(body,encoding='utf-8')
