from __future__ import annotations
from pathlib import Path
from datetime import datetime
from html import escape


def pct(x):
    try:
        return f"{x*100:+.2f}%"
    except Exception:
        return "-"


def score_word(p):
    if p >= .62:
        return "上向き材料が多い", "↑"
    if p >= .55:
        return "やや上向き", "↗"
    if p <= .38:
        return "下向き材料が多い", "↓"
    if p <= .45:
        return "やや下向き", "↘"
    return "まだ方向感なし", "→"


def factor_word(v):
    if v >= .12:
        return "強い追い風 ↑"
    if v >= .04:
        return "少し追い風 ↗"
    if v <= -.12:
        return "強い逆風 ↓"
    if v <= -.04:
        return "少し逆風 ↘"
    return "ほぼ中立 →"


def regime_word(key, value):
    if key == "risk_off":
        if value >= .20:
            return "守りに向かう空気"
        if value <= -.20:
            return "リスクを取りやすい空気"
        return "大きな偏りなし"
    if key == "oil_pressure":
        if value >= .15:
            return "原油上昇の圧力"
        if value <= -.15:
            return "原油下落の圧力"
        return "原油は大きな偏りなし"
    if key == "usd_rate_pressure":
        if value >= .15:
            return "ドルを支える力"
        if value <= -.15:
            return "ドルへの逆風"
        return "ドルへの力は中立"
    if key == "japan_risk":
        if value >= .15:
            return "日本株への逆風"
        if value <= -.15:
            return "日本株への追い風"
        return "日本株への力は中立"
    return "中立"


def accuracy_text(sc):
    total = sc.get("total", 0)
    correct = sc.get("correct", 0)
    if total == 0:
        return "まだ0回"
    if total < 20:
        return f"蓄積中 {total}回（まだ評価しない）"
    return f"{100*correct/total:.0f}%（{correct}/{total}）"


def latest_date(results, kinds):
    dates = [r.get("market_date") for r in results if r.get("kind") in kinds and r.get("market_date")]
    return max(dates) if dates else "-"


def render(cfg, regime, results, state, out="docs/index.html"):
    latest = state.get("runs", [])[-1] if state.get("runs") else {}
    timestamp = latest.get("timestamp", datetime.now().astimezone().isoformat())
    session = latest.get("session", "-")
    session_jp = "朝の予測" if session == "morning" else ("夜の答え合わせ" if session == "evening" else session)

    equity_date = latest_date(results, {"equity"})
    fx_date = latest_date(results, {"fx"})
    gold_date = latest_date(results, {"commodity"})

    valid = [r for r in results if r.get("price") is not None]
    focus = sorted(valid, key=lambda r: abs(r.get("probability_up", .5)-.5), reverse=True)[:3]

    focus_cards = []
    for r in focus:
        word, arrow = score_word(r["probability_up"])
        focus_cards.append(
            f"<div class='focus'><div class='focus-name'>{escape(r['name'])}</div>"
            f"<div class='focus-main'>{arrow} {escape(word)}</div>"
            f"<div class='muted'>上向き度 {r['probability_up']*100:.0f}/100</div></div>"
        )

    cards = []
    detail_rows = []
    for r in results:
        if r.get("price") is None:
            cards.append(f"<article class='asset'><h3>{escape(r['name'])}</h3><p>データ取得失敗</p></article>")
            continue
        sc = state.get("scores", {}).get(r["symbol"], {})
        word, arrow = score_word(r["probability_up"])
        price_factor = factor_word(r.get("price_score", 0.0))
        news_factor = factor_word(r.get("news_score", 0.0))
        macro_factor = factor_word(r.get("macro_score", 0.0))
        cards.append(f"""
<article class='asset'>
  <div class='asset-head'>
    <div><h3>{escape(r['name'])}</h3><div class='muted'>最新価格日 {escape(r.get('market_date','-'))}</div></div>
    <div class='signal'>{arrow}</div>
  </div>
  <div class='judgement'>{escape(word)}</div>
  <div class='scoreline'><span>下向き</span><div class='meter'><div class='mark' style='left:{r['probability_up']*100:.0f}%'></div></div><span>上向き</span></div>
  <div class='bigscore'>上向き度 <b>{r['probability_up']*100:.0f}/100</b></div>
  <div class='two'>
    <div><span class='label'>前の取引日から</span><b>{pct(r['day_change'])}</b></div>
    <div><span class='label'>5取引日の流れ</span><b>{pct(r['momentum5'])}</b></div>
  </div>
  <div class='why'>
    <b>なぜ？</b>
    <div>価格の流れ：{escape(price_factor)}</div>
    <div>ニュース：{escape(news_factor)}</div>
    <div>世界全体：{escape(macro_factor)}</div>
  </div>
  <div class='accuracy'>予測の成績：{escape(accuracy_text(sc))}</div>
</article>""")
        detail_rows.append(
            f"<tr><td>{escape(r['name'])}</td><td>{r['price']:.3f}</td><td>{pct(r['day_change'])}</td>"
            f"<td>{pct(r['momentum5'])}</td><td>{r['probability_up']*100:.0f}</td>"
            f"<td>{r.get('price_score',0):+.2f}</td><td>{r.get('news_score',0):+.2f}</td>"
            f"<td>{r.get('macro_score',0):+.2f}</td></tr>"
        )

    weather = [
        ("risk_off", "市場の怖がり度", "投資家が守りに逃げているかを見る"),
        ("usd_rate_pressure", "ドルへの力", "米金利やドル全体の強さを見る"),
        ("oil_pressure", "原油の圧力", "原油高・原油安が市場へ与える力を見る"),
        ("japan_risk", "日本株の風", "日本株全体への追い風・逆風を見る"),
    ]
    weather_html = "".join(
        f"<div class='weather'><span class='weather-title'>{title}</span>"
        f"<b>{escape(regime_word(key, regime.get(key,0)))}</b><small>{desc}</small>"
        f"<details><summary>数字を見る</summary><code>{regime.get(key,0):+.2f}</code></details></div>"
        for key, title, desc in weather
    )

    body=f"""<!doctype html><html lang='ja'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>市場農場</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui,-apple-system,"Yu Gothic",sans-serif;margin:0;background:#f4f5f7;color:#171717;line-height:1.65}}
main{{max-width:1080px;margin:auto;padding:18px}}h1{{margin-bottom:4px}}h2{{margin:0 0 12px}}h3{{margin:0;font-size:1.15rem}}
.card,.asset{{background:#fff;border:1px solid #e3e5e8;border-radius:16px;padding:18px;margin:14px 0}}
.lead{{font-size:1.04rem}}.muted,small{{color:#666}}.status{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.status>div,.weather,.focus{{background:#f7f8fa;border-radius:12px;padding:12px}}
.steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.step{{background:#f7f8fa;border-radius:12px;padding:12px}}.step b{{display:block;margin-bottom:4px}}
.focuses{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.focus-main{{font-size:1.1rem;font-weight:700;margin:4px 0}}.focus-name{{font-weight:700}}
.weather-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.weather{{display:flex;flex-direction:column;gap:3px}}.weather-title{{font-weight:700}}
.assets{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.asset{{margin:0}}.asset-head{{display:flex;justify-content:space-between;gap:10px}}.signal{{font-size:2rem;font-weight:800}}
.judgement{{font-size:1.25rem;font-weight:800;margin:12px 0 6px}}.scoreline{{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:8px;font-size:.78rem;color:#666}}
.meter{{height:10px;border-radius:999px;background:linear-gradient(90deg,#ddd 0 49%,#bbb 49% 51%,#ddd 51% 100%);position:relative}}
.mark{{position:absolute;top:-5px;width:4px;height:20px;background:#111;border-radius:4px;transform:translateX(-2px)}}
.bigscore{{margin:8px 0 12px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.two>div{{background:#f7f8fa;padding:10px;border-radius:10px}}.label{{display:block;font-size:.78rem;color:#666}}
.why{{margin-top:12px;padding-top:10px;border-top:1px solid #eee}}.why div{{margin-top:3px}}.accuracy{{margin-top:10px;color:#555;font-size:.9rem}}
details{{margin-top:8px}}summary{{cursor:pointer;font-weight:600}}table{{width:100%;border-collapse:collapse;font-size:.9rem}}th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:right}}th:first-child,td:first-child{{text-align:left}}
.note{{border-left:4px solid #777;padding-left:12px}}code{{font-size:.9rem}}
@media(max-width:760px){{.steps,.focuses,.weather-grid,.assets{{grid-template-columns:1fr}}main{{padding:12px}}.card,.asset{{padding:14px}}}}
</style></head><body><main>
<h1>市場農場</h1>
<p class='muted'>初心者表示｜最終実行 {escape(timestamp)} ｜ {escape(session_jp)}</p>

<section class='card'>
<h2>まず、ここだけ見ればいい</h2>
<div class='steps'>
  <div class='step'><b>① 世界の空模様</b>市場全体が「攻め」か「守り」かを見る。</div>
  <div class='step'><b>② 作物の矢印</b>↑なら上向き材料、↓なら下向き材料、→ならまだ分からない。</div>
  <div class='step'><b>③ 「なぜ？」</b>価格・ニュース・世界全体のどれが効いているかを見る。</div>
</div>
<p class='note'><b>上向き度は本当の確率ではありません。</b> 50が真ん中。70なら上向き材料がかなり多い、30なら下向き材料がかなり多い、という「力の偏り」を表します。</p>
</section>

<section class='card'>
<h2>データはいつのもの？</h2>
<div class='status'>
  <div><small>日本株</small><br><b>{escape(equity_date)}</b></div>
  <div><small>為替</small><br><b>{escape(fx_date)}</b></div>
  <div><small>金</small><br><b>{escape(gold_date)}</b></div>
  <div><small>システム最終実行</small><br><b>{escape(timestamp[:16].replace('T',' '))}</b></div>
</div>
<p class='muted'>「ページを更新した時刻」と「市場で最後に値段が付いた日」は別です。休場日にはページが更新されても株価は前の取引日のままです。</p>
</section>

<section class='card'>
<h2>今、モデルが強く反応しているもの</h2>
<p class='muted'>買えという意味ではなく、「上か下かの偏りが比較的大きいので観察すると勉強になる」という意味です。</p>
<div class='focuses'>{''.join(focus_cards)}</div>
</section>

<section class='card'>
<h2>世界の空模様</h2>
<p class='lead'>まずここで「畑全体の天気」を見る。個別株を見る前の背景です。</p>
<div class='weather-grid'>{weather_html}</div>
</section>

<section>
<h2>それぞれの作物</h2>
<p class='muted'>最初は「矢印 → なぜ？」だけで十分。価格そのものを暗記する必要はありません。</p>
<div class='assets'>{''.join(cards)}</div>
</section>

<section class='card'>
<details>
<summary>詳しい数字を見る（慣れてからでOK）</summary>
<div style='overflow:auto'><table><thead><tr><th>対象</th><th>価格</th><th>前日比</th><th>5日</th><th>上向き度</th><th>価格要因</th><th>ニュース</th><th>世界</th></tr></thead>
<tbody>{''.join(detail_rows)}</tbody></table></div>
</details>
</section>

<section class='card'>
<h2>この画面でまだ信用しすぎてはいけないところ</h2>
<p>予測実績はまだ数回しかありません。2回中2回当たっても「100%当たる」とは扱いません。少なくとも20〜30回以上ためてから、使えるセンサーと使えないセンサーを分けます。</p>
<p>現在は価格・簡易ニュース・世界全体の指標が中心です。今後、大口ポジション、中央銀行、ETF資金、SNS急増、祝日・取引時間を別センサーとして追加します。</p>
</section>

</main></body></html>"""
    p=Path(out)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(body,encoding="utf-8")
