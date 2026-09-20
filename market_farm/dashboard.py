from __future__ import annotations
from pathlib import Path
from datetime import datetime
from html import escape
import json


def pct(x):
    try:
        return f"{x*100:+.2f}%"
    except Exception:
        return "-"


def direction_word(p):
    if p >= .62:
        return "上がる側の材料が多い", "↑"
    if p >= .55:
        return "少し上がる側", "↗"
    if p <= .38:
        return "下がる側の材料が多い", "↓"
    if p <= .45:
        return "少し下がる側", "↘"
    return "まだどちらとも言えない", "→"


def simple_force(v):
    if v >= .12:
        return "上がる側へ強め"
    if v >= .04:
        return "上がる側へ少し"
    if v <= -.12:
        return "下がる側へ強め"
    if v <= -.04:
        return "下がる側へ少し"
    return "ほぼ真ん中"


def world_word(key, value):
    if key == "risk_off":
        if value >= .20:
            return "みんな少し怖がっている"
        if value <= -.20:
            return "みんな少し攻め気味"
        return "大きな偏りなし"
    if key == "usd_rate_pressure":
        if value >= .15:
            return "ドルに追い風"
        if value <= -.15:
            return "ドルに逆風"
        return "ほぼ真ん中"
    if key == "oil_pressure":
        if value >= .15:
            return "原油は上向き"
        if value <= -.15:
            return "原油は下向き"
        return "大きな動きなし"
    if key == "japan_risk":
        if value >= .15:
            return "日本株に逆風"
        if value <= -.15:
            return "日本株に追い風"
        return "ほぼ真ん中"
    return "ほぼ真ん中"


def accuracy_text(sc):
    total = sc.get("total", 0)
    correct = sc.get("correct", 0)
    if total == 0:
        return "まだ答え合わせなし"
    if total < 20:
        return f"{total}回答え合わせ済み（まだ少なすぎる）"
    return f"{total}回答え合わせ済み / 正解 {100*correct/total:.0f}%"


def latest_date(results, kinds, backtest=None):
    dates = [r.get("market_date") for r in results if r.get("kind") in kinds and r.get("market_date")]
    if dates:
        return max(dates)
    if backtest:
        hist_dates = [
            row.get("available_end") for row in backtest.get("assets", {}).values()
            if row.get("kind") in kinds and row.get("available_end")
        ]
        if hist_dates:
            return max(hist_dates)
    return "-"


def historical_cell(window):
    if not window or window.get("accuracy") is None:
        return "データ不足"
    return f"正解 {window['accuracy']*100:.0f}% / {window.get('signals',0)}回"


def direction_jp(value):
    return {"UP": "↑ 上", "DOWN": "↓ 下", "FLAT": "→ 横ばい"}.get(value, "-")


def recent_score_cell(score):
    if not score or score.get("accuracy") is None:
        return "まだ判定なし"
    return f"正解 {score['accuracy']*100:.0f}% / {score.get('signals',0)}回"


def outside_sources(symbol, kind):
    if symbol == "USDJPY=X":
        return "米10年金利・ドル指数・原油"
    if symbol == "EURJPY=X":
        return "世界の怖がり度・原油"
    if symbol == "CHFJPY=X":
        return "世界の怖がり度・ドルの強さ"
    if symbol == "GC=F":
        return "世界の怖がり度・ドルの強さ"
    if kind == "equity":
        return "世界の怖がり度（VIXとS&P500）"
    return "世界の市場データ"


def render(cfg, regime, results, state, out="docs/index.html"):
    latest = state.get("runs", [])[-1] if state.get("runs") else {}
    timestamp = latest.get("timestamp", datetime.now().astimezone().isoformat())
    session = latest.get("session", "-")
    session_jp = "朝の予想" if session == "morning" else ("夜の答え合わせ" if session == "evening" else session)

    backtest = {}
    backtest_path = Path("data/backtest.json")
    if backtest_path.exists():
        try:
            backtest = json.loads(backtest_path.read_text(encoding="utf-8"))
        except Exception:
            backtest = {}

    recent = {}
    recent_path = Path("data/recent_news_backtest.json")
    if recent_path.exists():
        try:
            recent = json.loads(recent_path.read_text(encoding="utf-8"))
        except Exception:
            recent = {}

    cards_index = {}
    cards_index_path = Path("data/cards_index.json")
    if cards_index_path.exists():
        try:
            cards_index = json.loads(cards_index_path.read_text(encoding="utf-8"))
        except Exception:
            cards_index = {}

    replay_index = {}
    replay_index_path = Path("data/replay_index.json")
    if replay_index_path.exists():
        try:
            replay_index = json.loads(replay_index_path.read_text(encoding="utf-8"))
        except Exception:
            replay_index = {}

    replay_latest = {}
    completed_months = replay_index.get("completed_months", [])
    if completed_months:
        replay_path = Path("data/replay") / f"{completed_months[0]}.json"
        if replay_path.exists():
            try:
                replay_latest = json.loads(replay_path.read_text(encoding="utf-8"))
            except Exception:
                replay_latest = {}

    equity_date = latest_date(results, {"equity"}, backtest)
    fx_date = latest_date(results, {"fx"}, backtest)
    gold_date = latest_date(results, {"commodity"}, backtest)

    valid = [r for r in results if r.get("price") is not None]
    focus = sorted(valid, key=lambda r: abs(r.get("probability_up", .5)-.5), reverse=True)[:3]

    focus_cards = []
    for r in focus:
        word, arrow = direction_word(r["probability_up"])
        focus_cards.append(
            f"<div class='mini'><b>{escape(r['name'])}</b>"
            f"<div class='big'>{arrow} {escape(word)}</div>"
            f"<small>予測器の向きメーター {r['probability_up']*100:.0f}/100</small></div>"
        )

    cards = []
    for r in results:
        if r.get("price") is None:
            cards.append(f"<article class='asset'><h3>{escape(r['name'])}</h3><p>今日はデータを取れませんでした。</p></article>")
            continue

        sc = state.get("scores", {}).get(r["symbol"], {})
        word, arrow = direction_word(r["probability_up"])
        price_factor = simple_force(r.get("price_score", 0.0))
        news_factor = simple_force(r.get("news_score", 0.0))
        macro_factor = simple_force(r.get("macro_score", 0.0))
        market_date = r.get("market_date") or backtest.get("assets", {}).get(r["symbol"], {}).get("available_end", "-")
        outside = outside_sources(r["symbol"], r["kind"])

        cards.append(f"""
<article class='asset'>
  <div class='asset-head'>
    <div>
      <h3>{escape(r['name'])}</h3>
      <small>この値段が付いた日：{escape(str(market_date))}</small>
    </div>
    <div class='arrow'>{arrow}</div>
  </div>

  <div class='answer'>次の取引日：<b>{escape(word)}</b></div>
  <p class='plain'>これは「長期で成長する会社か」ではなく、<b>次の取引日の上・下どちらに材料が寄っているか</b>です。</p>

  <div class='meterrow'>
    <span>下がる側</span>
    <div class='meter'><i style='left:{r["probability_up"]*100:.0f}%'></i></div>
    <span>上がる側</span>
  </div>
  <div class='center'>向きメーター <b>{r['probability_up']*100:.0f}/100</b>　※確率ではない</div>

  <div class='reasons'>
    <div>
      <b>① この銘柄自身の勢い</b>
      <strong>{escape(price_factor)}</strong>
      <small>最近5取引日の動きと、「最近5日の平均」と「最近20日の平均」を比べています。</small>
    </div>
    <div>
      <b>② この銘柄のニュース</b>
      <strong>{escape(news_factor)}</strong>
      <small>Googleニュースの最近の見出しに、増益・上方修正などの言葉と、減益・下方修正などの言葉のどちらが多いかを簡単に数えています。世間全体の人気ではありません。</small>
    </div>
    <div>
      <b>③ 外から吹く風</b>
      <strong>{escape(macro_factor)}</strong>
      <small>この対象では主に「{escape(outside)}」を見ています。世界の全部を見ているわけではありません。</small>
    </div>
  </div>

  <details>
    <summary>値段の数字も見る</summary>
    <p>最新価格：{r['price']:.3f}<br>前の取引日から：{pct(r['day_change'])}<br>5取引日前から：{pct(r['momentum5'])}</p>
  </details>

  <p class='score-note'>これからの本番成績：{escape(accuracy_text(sc))}</p>
</article>""")

    weather = [
        ("risk_off", "世界は怖がってる？", "VIXが上がったか、S&P500が下がったかを主に5取引日で比べます。怖がる人が増えると、株から逃げる動きが出やすくなります。"),
        ("usd_rate_pressure", "ドルに風は吹いてる？", "米10年金利とドル指数の最近5取引日の動きを合わせて見ます。ドル円や金に関係しやすい材料です。"),
        ("oil_pressure", "原油は上がってる？", "原油価格を5取引日前と比べます。日本は原油を輸入するので、円や企業コストを見る材料の一つです。"),
        ("japan_risk", "日本株全体は元気？", "日経平均の最近5取引日の動きを見ます。今は背景表示が中心で、個別株の点数にはまだ強く使っていません。"),
    ]
    weather_html = "".join(
        f"<div class='weather'><b>{escape(title)}</b><div class='big'>{escape(world_word(key, regime.get(key,0)))}</div>"
        f"<small>{escape(desc)}</small><details><summary>元の点数を見る</summary><code>{regime.get(key,0):+.2f}</code></details></div>"
        for key, title, desc in weather
    )

    history_rows = []
    for asset in cfg.get("assets", []):
        h = backtest.get("assets", {}).get(asset["symbol"], {})
        ws = h.get("windows", {})
        if h.get("error") or not ws:
            history_rows.append(f"<tr><td>{escape(asset['name'])}</td><td colspan='4'>まだ検証できていません</td></tr>")
            continue
        history_rows.append(
            f"<tr><td>{escape(asset['name'])}</td>"
            f"<td>{escape(historical_cell(ws.get('1y')))}</td>"
            f"<td>{escape(historical_cell(ws.get('3y')))}</td>"
            f"<td>{escape(historical_cell(ws.get('5y')))}</td>"
            f"<td>{escape(h.get('available_start','-'))}〜{escape(h.get('available_end','-'))}</td></tr>"
        )

    recent_rows = []
    recent_audits = []
    for asset in cfg.get("assets", []):
        rr = recent.get("assets", {}).get(asset["symbol"], {})
        with_news = rr.get("with_news", {})
        without_news = rr.get("without_news", {})
        aw = with_news.get("accuracy")
        ab = without_news.get("accuracy")
        if aw is not None and ab is not None:
            delta = aw - ab
            delta_text = f"{delta*100:+.0f}ポイント"
        else:
            delta_text = "-"
        recent_rows.append(
            f"<tr><td>{escape(asset['name'])}</td>"
            f"<td>{escape(recent_score_cell(without_news))}</td>"
            f"<td>{escape(recent_score_cell(with_news))}</td>"
            f"<td>{escape(delta_text)}</td>"
            f"<td>{rr.get('archive_articles',0)}件</td></tr>"
        )

        rows = rr.get("rows", [])
        sample_rows = []
        for item in rows[-5:]:
            mark = "○" if item.get("news_correct") else "×"
            sample_rows.append(
                f"<tr><td>{escape(item.get('target_date','-'))}</td>"
                f"<td>{escape(item.get('information_cutoff_jst','-')[:19].replace('T',' '))}</td>"
                f"<td>{escape(item.get('price_data_through','-'))}</td>"
                f"<td>{item.get('asset_news_count',0)}件</td>"
                f"<td>{escape(direction_jp(item.get('news_direction')))}</td>"
                f"<td>{escape(direction_jp(item.get('actual_direction')))}</td>"
                f"<td>{mark}</td></tr>"
            )
        if sample_rows:
            recent_audits.append(
                f"<details><summary>{escape(asset['name'])}：実際の締切を確認</summary>"
                f"<div style='overflow:auto'><table><thead><tr><th>予測する日</th><th>情報の締切</th>"
                f"<th>価格はここまで</th><th>使ったニュース</th><th>予測</th><th>実際</th><th>結果</th></tr></thead>"
                f"<tbody>{''.join(sample_rows)}</tbody></table></div></details>"
            )

    recent_overall = recent.get("overall", {})
    recent_generated = recent.get("generated_at", "-")

    replay_examples = []
    for asset in cfg.get("assets", [])[:4]:
        rr = replay_latest.get("assets", {}).get(asset["symbol"], {})
        rows = rr.get("snapshots", [])
        if not rows:
            continue
        item = rows[-1]
        h1 = item.get("horizons", {}).get("next_day") or {}
        h2 = item.get("horizons", {}).get("two_days") or {}
        hm = item.get("horizons", {}).get("one_month") or {}
        replay_examples.append(
            f"<tr><td>{escape(asset['name'])}</td>"
            f"<td>{escape(item.get('as_of_date','-'))}</td>"
            f"<td>{escape(item.get('information_cutoff_jst','-')[:19].replace('T',' '))}</td>"
            f"<td>{item.get('asset_news_count_72h',0)}件</td>"
            f"<td>{escape(direction_jp(item.get('prediction_direction')))}</td>"
            f"<td>{escape(direction_jp(h1.get('direction')))}</td>"
            f"<td>{escape(direction_jp(h2.get('direction')))}</td>"
            f"<td>{escape(direction_jp(hm.get('direction')))}</td></tr>"
        )

    card_rows = []
    for item in cards_index.get("recent", [])[:8]:
        result = "-"
        if item.get("status") == "SETTLED":
            result = "○" if item.get("correct") else "×"
        card_rows.append(
            f"<tr><td>{escape(str(item.get('prediction_date','-')))}</td>"
            f"<td>{escape(str(item.get('name','-')))}</td>"
            f"<td>{escape(direction_jp(item.get('direction')))}</td>"
            f"<td>{escape(str(item.get('market_data_through','-')))}</td>"
            f"<td>{escape(str(item.get('status','-')))}</td>"
            f"<td>{result}</td>"
            f"<td>{escape(str(item.get('result_type') or '-'))}</td></tr>"
        )
    cards_accuracy = cards_index.get("accuracy")
    cards_accuracy_text = "-" if cards_accuracy is None else f"{cards_accuracy*100:.0f}%"

    replay_months = replay_index.get("months_completed", 0)
    replay_next = replay_index.get("next_month", "-")
    replay_oldest = replay_index.get("oldest_month", "-")
    replay_range = "-"
    if completed_months:
        replay_range = f"{completed_months[-1]} 〜 {completed_months[0]}"

    body = f"""<!doctype html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>市場農場</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f3f5f6;color:#171717;font-family:system-ui,-apple-system,"Yu Gothic",sans-serif;line-height:1.7}}
main{{max-width:1050px;margin:auto;padding:16px}}
h1{{margin:0}}h2{{margin:0 0 10px}}h3{{margin:0}}
.card,.asset{{background:white;border:1px solid #e1e4e7;border-radius:16px;padding:18px;margin:14px 0}}
.hero{{border:2px solid #222}}
.hero .purpose{{font-size:1.25rem;font-weight:800;margin:8px 0}}
.remember{{background:#f7f8f9;border-radius:12px;padding:14px;margin-top:12px}}
.remember b{{display:block;font-size:1.05rem}}
.auto{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}
.auto>div,.mini,.weather,.reasons>div,.dates>div{{background:#f7f8f9;border-radius:12px;padding:12px}}
.small,.muted,small{{color:#60666c}}
.focuses{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.big{{font-size:1.08rem;font-weight:800;margin:4px 0}}
.weather-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}
.weather{{display:flex;flex-direction:column;gap:4px}}
.dates{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.assets{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}
.asset{{margin:0}}
.asset-head{{display:flex;justify-content:space-between;gap:8px}}
.arrow{{font-size:2.2rem;font-weight:900}}
.answer{{font-size:1.2rem;margin:12px 0 4px}}
.plain{{font-size:.95rem;background:#fafafa;padding:10px;border-radius:10px}}
.meterrow{{display:grid;grid-template-columns:auto 1fr auto;gap:7px;align-items:center;font-size:.78rem;color:#666}}
.meter{{height:10px;background:#dedede;border-radius:999px;position:relative}}
.meter:after{{content:"";position:absolute;left:50%;top:0;width:2px;height:100%;background:#999}}
.meter i{{position:absolute;top:-5px;width:4px;height:20px;background:#111;border-radius:4px;transform:translateX(-2px)}}
.center{{text-align:center;margin:8px 0}}
.reasons{{display:grid;gap:8px;margin-top:12px}}
.reasons>div{{display:flex;flex-direction:column;gap:2px}}
.reasons strong{{font-size:1.02rem}}
.score-note{{font-size:.9rem;color:#555}}
table{{width:100%;border-collapse:collapse;font-size:.9rem}}
th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
details{{margin-top:8px}}summary{{cursor:pointer;font-weight:700}}
.note{{border-left:4px solid #777;padding-left:12px}}
@media(max-width:760px){{
  main{{padding:10px}}
  .card,.asset{{padding:14px}}
  .auto,.focuses,.weather-grid,.dates,.assets{{grid-template-columns:1fr}}
}}
</style>
</head>
<body><main>

<section class='card hero'>
<h1>市場農場</h1>
<p><a href='./newspaper.html'><b>→ 朝刊だけ読む（初心者向け）</b></a>　｜　<a href='./research.html'><b>研究レポートを見る</b></a></p>
<div class='purpose'>世界のお金の動きを、毎日見て覚えるための練習場</div>
<p>これは「絶対に上がる株を教える機械」ではありません。<b>株・為替・金がなぜ動くのかを、いくつかの力に分けて観察し、本当に予測に役立つ力を探す実験</b>です。</p>
<div class='remember'>
<b>忘れたら、これだけ思い出せばOK</b>
① 世界全体の風を見る → ② 気になる株や通貨の向きを見る → ③ 「なぜ？」で理由を見る → ④ 何日もためて、本当に当たる方法か確かめる。
</div>
</section>

<section class='card'>
<h2>俺は何もしなくていいの？</h2>
<p><b>基本は、何もしなくて大丈夫です。</b> 自宅PCではなくGitHubのクラウド上で動きます。</p>
<div class='auto'>
  <div><b>平日 朝8:07ごろ</b><small>値段とニュースを自動取得して、その日の向きを予想。</small></div>
  <div><b>平日 夜20:07ごろ</b><small>もう一度取得して、朝の予想の答え合わせ。</small></div>
  <div><b>日曜 朝9:37ごろ</b><small>最大5年の過去データで、この予測法を再テスト。</small></div>
  <div><b>日曜 朝10:17ごろ</b><small>直近約1か月を、当時のニュースまで使ってタイムマシン検証。</small></div>
  <div><b>毎日 朝10:47ごろ</b><small>さらに過去へ1か月ずつ遡り、歴史再現庫を増やす。</small></div>
  <div><b>そのあと</b><small>GitHub Pagesを自動更新。スマホはこのページを見るだけ。</small></div>
</div>
<p class='muted'>日々の値段は yfinance、日々のニュース見出しは Google News RSS。直近約1か月の過去ニュース検証は GDELT のニュースアーカイブを使います。GitHub側の混雑や取得先の障害で欠けることはあります。秒単位の売買用ではありません。</p>
</section>

<section class='card'>
<h2>今日は、いつのデータ？</h2>
<div class='dates'>
  <div><small>日本株</small><br><b>{escape(equity_date)}</b></div>
  <div><small>為替</small><br><b>{escape(fx_date)}</b></div>
  <div><small>金</small><br><b>{escape(gold_date)}</b></div>
  <div><small>システム最終実行</small><br><b>{escape(timestamp[:16].replace("T"," "))}</b></div>
</div>
<p class='muted'>休みの日は、ページが動いても株の値段は前の取引日のままです。同じ取引日の値段しかない場合は、これからは答え合わせ回数に数えません。</p>
</section>

<section class='card'>
<h2>① 世界全体の風を見る</h2>
<p>「今日は株を買いたい空気？ 守りたい空気？ ドルは強い？ 原油は？」をざっくり見る場所です。</p>
<div class='weather-grid'>{weather_html}</div>
</section>

<section class='card'>
<h2>② 今日、予測器が一番はっきり向きを出した3つ</h2>
<p class='note'><b>おすすめ3銘柄ではありません。</b> ただ「上か下かの偏りが大きかった3つ」です。観察教材として目立たせています。</p>
<div class='focuses'>{''.join(focus_cards)}</div>
</section>

<section>
<h2>③ それぞれの「なぜ？」を見る</h2>
<p class='muted'>各カードは3つだけ見ます。「自分の勢い」「ニュース」「外からの風」です。</p>
<div class='assets'>{''.join(cards)}</div>
</section>

<section class='card'>
<h2>④ 5年の基礎テスト：ニュース抜きで何が効く？</h2>
<p><b>これは今の完成版予測器の成績ではありません。</b> 実際の過去価格・VIX・S&P500・米10年金利・ドル指数・原油・日経平均など、長くそろう市場データだけを使った「土台の実験」です。</p>
<p class='note'><b>目的：</b>「価格の勢い」や「外からの風」だけに予測力があるかを、たくさんの日数で確認すること。ニュースや詳しい経済統計が無いので、この成績をそのまま本番モデルの実力とは呼びません。</p>
<div class='remember'>
<b>表の読み方</b>
「515回」＝その期間に予測器が <b>↑か↓をはっきり出した日が515回</b>。<br>
「正解36%」＝その515回のうち、<b>次の取引日に実際に同じ向きだった割合</b>。<br>
「→ まだ分からない」と答えた日は、この回数に入れていません。
</div>
<p class='muted'>長所：何百〜千回単位で試せるので、基礎センサーの癖を見つけやすい。短所：当時のニュース・CPI・雇用統計・中央銀行発言などを全部再現しているわけではない。だから「5年の数字」と「ニュース込みの数字」は混ぜません。</p>
<div style='overflow:auto'><table>
<thead><tr><th>対象</th><th>過去1年</th><th>過去3年</th><th>最大5年</th><th>使えた期間</th></tr></thead>
<tbody>{''.join(history_rows)}</tbody>
</table></div>
</section>

<section class='card'>
<h2>⑤ 直近約1か月の再現テスト：当時のニュースも入れる</h2>
<p><b>こちらは情報の種類が多い代わりに、まだ日数が少ないテストです。</b> 5年テストより「その日に人が見えていた世界」に近づけますが、1か月だけで強い結論は出しません。</p>
<div class='remember'>
<b>例：8月20日を予測するなら</b>
価格は8月19日まで。ニュースも<b>8月19日23:59:59（日本時間）までに確認できた記事だけ</b>。8月20日の値段は、予測を作る時には使わず、最後の答え合わせだけに使います。
</div>
<p>「ニュースなし」と「当時のニュースあり」を同じ期間で並べて、<b>ニュースを足したことで本当に良くなったか</b>を比べます。ここで改善しても、次は未来の本番観測で確認します。</p>
<div style='overflow:auto'><table>
<thead><tr><th>対象</th><th>ニュースなし</th><th>当時ニュースあり</th><th>差</th><th>取得した記事</th></tr></thead>
<tbody>{''.join(recent_rows)}</tbody>
</table></div>
<p class='muted'>今のニュース判定は見出しの単純な言葉判定なので、良くなるとは限りません。世界ニュースも同じ締切で保存していますが、まだ予測点数には入れず「あとで効くか試す材料」として残しています。更新: {escape(str(recent_generated))}</p>
{''.join(recent_audits) if recent_audits else "<p>初回のタイムマシン検証を準備中です。</p>"}
</section>

<section class='card'>
<h2>⑥ 過去を1か月ずつ掘る「歴史再現庫」</h2>
<p><b>これが今追加した、本格的な積み上げ部分です。</b> 毎日1か月ずつ過去へ戻り、その月の各取引日について「その日の23:59までに見えていた価格・市場指標・ニュース」だけを保存します。</p>
<div class='remember'>
<b>1日分の記録に残すもの</b>
その時点の日付 / 情報の締切 / 価格 / 72時間以内のニュース / 世界ニュース / その時の予測 / 翌日・2取引日後・約1か月後の実際。
</div>
<div class='dates'>
  <div><small>掘り終えた月</small><br><b>{replay_months}か月</b></div>
  <div><small>現在の範囲</small><br><b>{escape(replay_range)}</b></div>
  <div><small>次に掘る月</small><br><b>{escape(str(replay_next))}</b></div>
  <div><small>いちばん古い目標</small><br><b>{escape(str(replay_oldest))}</b></div>
</div>
<p class='muted'>1日1か月ずつ進めるので、完成した記録はあとから消さずに積み上げます。ニュース取得が上限に当たった月や取得失敗は、その事実も記録します。</p>
{("<div style='overflow:auto'><table><thead><tr><th>対象</th><th>その時点</th><th>情報締切</th><th>ニュース</th><th>当時の予測</th><th>翌日実際</th><th>2日後実際</th><th>約1か月後実際</th></tr></thead><tbody>" + ''.join(replay_examples) + "</tbody></table></div>") if replay_examples else "<p>最初の1か月分を作成中です。</p>"}
<p class='note'><b>大事：</b>いまは同じ「その時点の向き」を1日後・2日後・20取引日後で採点しています。十分な月数がたまったら、明日用・2日後用・1か月用を別々の予測器に育てます。先に結果を見てルールを作らないためです。</p>
</section>

<section class='card'>
<h2>3つの成績は混ぜない</h2>
<div class='remember'>
<b>① 5年の基礎テスト</b>
長い。だけど情報は少なめ。価格・金利系・市場指標の土台を調べる。<br><br>
<b>② 1か月の再現テスト</b>
短い。だけど当時ニュースも入る。「ニュースを足す価値」を調べる。<br><br>
<b>③ これからの本番テスト</b>
いちばん大事。朝に予測を固定して、未来の結果で答え合わせする。
</div>
<p><b>この3つは別々に保存・表示します。</b> 5年の成績を、ニュース込みモデルの成績として水増ししません。</p>
</section>

<section class='card'>
<h2>⑦ 本番の「予測カルテ」</h2>
<p><b>朝の予測を作った瞬間に、その時見ていた証拠ごと固定保存します。</b> あとから予測ルールを直しても、昔のカルテは昔のまま残します。</p>
<div class='dates'>
  <div><small>カルテ総数</small><br><b>{cards_index.get('cards_total',0)}</b></div>
  <div><small>まだ答え待ち</small><br><b>{cards_index.get('cards_open',0)}</b></div>
  <div><small>答え合わせ済み</small><br><b>{cards_index.get('cards_settled',0)}</b></div>
  <div><small>本番正解率</small><br><b>{escape(cards_accuracy_text)}</b></div>
</div>
<div class='remember'>
<b>1枚のカルテに固定するもの</b>
予測日時 / モデルの版 / 価格データは何日までか / 最近の価格の勢い / その時読めたニュース見出し / 外からの風 / 現行モデルの予測 / 挑戦者モデルの予測。<br><br>
答えが出た後にだけ、実際の値動きと「方向を逆に読んだ」「動きを見逃した」などの反省を追記します。
</div>
{("<div style='overflow:auto'><table><thead><tr><th>予測日</th><th>対象</th><th>予測</th><th>価格データ</th><th>状態</th><th>結果</th><th>反省</th></tr></thead><tbody>" + ''.join(card_rows) + "</tbody></table></div>") if card_rows else "<p>次の朝の本番予測からカルテが自動で作られます。</p>"}
<p class='muted'>この反省分類は機械的な整理です。「これが原因だった」と断定するものではありません。因果関係は、カルテがたまった後に僕と一緒に複数例を比べて調べます。</p>
</section>

<section class='card'>
<h2>いま何を育てているの？</h2>
<p>今は「価格」「ニュース見出し」「世界の市場データ」の小さな農場です。5年の広い検証に加えて、直近約1か月はニュースも当時の締切で再現します。これから、中央銀行、大口投資家の動き、ETFへのお金の出入り、SNSの急増などを<b>別々のセンサー</b>として追加し、何を足した時だけ本当に成績が良くなるか比べます。</p>
<p><b>情報を増やすこと自体が目的ではありません。</b> 入れたセンサーが役に立たなければ捨てます。最終目的は「世界の動きを理解しやすく分解して、自分で理由を考えられるようにすること」です。</p>
</section>

</main></body></html>"""

    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
