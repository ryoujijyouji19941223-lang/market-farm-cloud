from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime


def pct(x):
    try:
        return f"{x*100:+.2f}%"
    except Exception:
        return "-"


def arrow(prob):
    if prob >= .62:
        return "↑", "上がる側の材料が多め"
    if prob >= .55:
        return "↗", "少し上がる側"
    if prob <= .38:
        return "↓", "下がる側の材料が多め"
    if prob <= .45:
        return "↘", "少し下がる側"
    return "→", "まだはっきりしない"


def force(v):
    if v >= .12:
        return "強い追い風"
    if v >= .04:
        return "少し追い風"
    if v <= -.12:
        return "強い逆風"
    if v <= -.04:
        return "少し逆風"
    return "ほぼ中立"


def market_weather(regime):
    risk = regime.get("risk_off", 0.0)
    usd = regime.get("usd_rate_pressure", 0.0)
    oil = regime.get("oil_pressure", 0.0)
    jp = regime.get("japan_risk", 0.0)

    if risk >= .20:
        mood = "投資家は少し守り気味"
    elif risk <= -.20:
        mood = "投資家は少し攻め気味"
    else:
        mood = "世界全体は大きく偏っていない"

    if usd >= .15:
        dollar = "ドルには追い風"
    elif usd <= -.15:
        dollar = "ドルには逆風"
    else:
        dollar = "ドルへの風は弱い"

    if oil >= .15:
        oil_txt = "原油は上向き"
    elif oil <= -.15:
        oil_txt = "原油は下向き"
    else:
        oil_txt = "原油は落ち着き気味"

    if jp >= .15:
        japan = "日本株には逆風"
    elif jp <= -.15:
        japan = "日本株には追い風"
    else:
        japan = "日本株全体への風は弱い"

    return mood, dollar, oil_txt, japan


def next_watch(r):
    symbol = r["symbol"]
    kind = r["kind"]

    if symbol == "USDJPY=X":
        return [
            "米国の長期金利が上がる → ドル高・円安側の材料になりやすい",
            "日銀が利上げ寄りになる → 円高側の材料になりやすい",
            "市場が急に怖がる → 円の買い戻しが起きるかを見る",
        ]
    if symbol == "EURJPY=X":
        return [
            "ECBが利下げ寄り → ユーロには逆風になりやすい",
            "日銀が利上げ寄り → 円高側の材料になりやすい",
            "欧州景気の強弱を見る",
        ]
    if symbol == "CHFJPY=X":
        return [
            "世界の不安が強まる → スイスフランに資金が逃げるかを見る",
            "SNBの金利姿勢を見る",
            "日銀が利上げ寄り → 円側が強くなる可能性を見る",
        ]
    if symbol == "GC=F":
        return [
            "米金利低下 → 金には追い風になりやすい",
            "戦争・金融不安の強まり → 安全資産需要を見る",
            "ドル高 → 金には逆風になりやすい",
        ]
    if kind == "equity":
        return [
            "会社自身の新しい材料（決算・受注・新商品）が出るか",
            "日経平均や米国株が大きく崩れていないか",
            "ニュースと株価が同じ方向に動いているか",
        ]
    return ["新しい材料が出たか", "価格の流れが変わったか", "外からの風が変わったか"]


def likely_story(r, causal_news):
    parts = []
    day = r.get("day_change", 0.0)
    price = r.get("price_score", 0.0)
    news = 0.0
    if causal_news:
        from .news import sentiment
        news = sentiment([{"title": x.get("title",""), "link": x.get("link","")} for x in causal_news])
    macro = r.get("macro_score", 0.0)

    if abs(day) >= .01:
        parts.append(f"前の取引日から {pct(day)} と比較的大きく動いた")
    else:
        parts.append(f"前の取引日から {pct(day)} で、値動きは比較的小さい")

    if abs(news) >= .04:
        parts.append(f"値動きより前に確認できた関連ニュースは「{force(news)}」側")
    if abs(macro) >= .04:
        parts.append(f"外部環境は「{force(macro)}」側")
    if abs(price) >= .04:
        parts.append(f"最近の値動き自体は「{force(price)}」側")

    return "。".join(parts) + "。"


def _strict_terms(r):
    mapping = {
        "7974.T": ["任天堂", "nintendo"],
        "8316.T": ["三井住友", "smfg", "sumitomo mitsui"],
        "285A.T": ["キオクシア", "kioxia"],
        "8136.T": ["サンリオ", "sanrio", "hello kitty"],
        "5401.T": ["日本製鉄", "nippon steel", "us steel"],
        "6522.T": ["アスタリスク", "asterisk"],
        "1736.T": ["オーテック", "otec"],
        "3656.T": ["klab"],
    }
    return mapping.get(r.get("symbol"), [])


def _published_date(item):
    raw = item.get("published_at", "")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).date()
    except Exception:
        return None


def relevant_news(r, before_market_close=False):
    items = r.get("news", [])
    terms = _strict_terms(r)
    market_date = None
    try:
        market_date = datetime.fromisoformat(str(r.get("market_date"))).date()
    except Exception:
        pass

    filtered = []
    for item in items:
        title = item.get("title", "").lower()
        if terms and not any(term.lower() in title for term in terms):
            continue
        if before_market_close and market_date is not None:
            pub = _published_date(item)
            if pub is not None and pub > market_date:
                continue
        filtered.append(item)
    return filtered[:3]


def news_items(items, empty_text):
    if not items:
        return f"<p class='muted'>{escape(empty_text)}</p>"
    out = []
    for item in items:
        title = escape(item.get("title", ""))
        link = escape(item.get("link", ""))
        if link:
            out.append(f"<li><a href='{link}' target='_blank' rel='noopener'>{title}</a></li>")
        else:
            out.append(f"<li>{title}</li>")
    return "<ul>" + "".join(out) + "</ul>"


def render_newspaper(cfg, regime, results, out="docs/newspaper.html"):
    tz = ZoneInfo(cfg.get("timezone", "Asia/Tokyo"))
    now = datetime.now(tz)

    valid = [r for r in results if r.get("price") is not None]
    movers = sorted(valid, key=lambda r: abs(r.get("day_change", 0.0)), reverse=True)[:4]
    focus = sorted(valid, key=lambda r: abs(r.get("probability_up", .5)-.5), reverse=True)[:3]
    mood, dollar, oil_txt, japan = market_weather(regime)

    focus_html = []
    for r in focus:
        a, label = arrow(r.get("probability_up", .5))
        focus_html.append(
            f"<div class='brief'><b>{escape(r['name'])}</b>"
            f"<span class='big'>{a} {escape(label)}</span>"
            f"<small>向きメーター {r.get('probability_up',.5)*100:.0f}/100</small></div>"
        )

    stories = []
    for r in movers:
        a, label = arrow(r.get("probability_up", .5))
        watches = "".join(f"<li>{escape(x)}</li>" for x in next_watch(r))
        causal_news = relevant_news(r, before_market_close=True)
        latest_news = relevant_news(r, before_market_close=False)
        stories.append(f"""
<article class='story'>
  <div class='story-head'>
    <div><h3>{escape(r['name'])}</h3><small>最新価格日 {escape(str(r.get('market_date','-')))}</small></div>
    <div class='move'>{pct(r.get('day_change',0.0))}</div>
  </div>
  <p><b>何が起きた？</b><br>{escape(likely_story(r, causal_news))}</p>
  <p><b>値動きより前に出ていた関連ニュース</b></p>
  {news_items(causal_news, "株価が動く前の関連見出しを十分に確認できませんでした。無理に原因を決めません。")}
  <p class='caution'>※ここに記事があっても、それだけで値動きの原因とは断定しません。原因候補として扱います。</p>
  <p><b>今朝までの新しい関連ニュース</b></p>
  {news_items(latest_news, "銘柄名と直接結びつく新しい見出しは見つかりませんでした。")}
  <div class='prediction'><b>市場農場の今の見方：</b> {a} {escape(label)}</div>
  <p><b>次に何を見ればいい？</b></p>
  <ul>{watches}</ul>
</article>""")

    html = f"""<!doctype html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>市場農場 朝刊</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f5f3ee;color:#1d1d1b;font-family:system-ui,-apple-system,"Yu Gothic",sans-serif;line-height:1.75}}
main{{max-width:900px;margin:auto;padding:14px}}
a{{color:inherit}}
.paper{{background:#fff;border:1px solid #ddd7cc;border-radius:14px;padding:18px;margin:14px 0}}
.mast{{border-top:5px solid #111;border-bottom:2px solid #111;padding:14px 0;margin-bottom:14px}}
.mast h1{{margin:0;font-size:2rem;letter-spacing:.08em}}
.mast p{{margin:2px 0;color:#666}}
.lead{{font-size:1.18rem;font-weight:700}}
.weather{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}
.weather>div,.brief{{background:#f5f5f3;border-radius:10px;padding:12px}}
.focuses{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.brief{{display:flex;flex-direction:column}}
.big{{font-size:1.08rem;font-weight:800;margin:4px 0}}
.story{{border-top:1px solid #ddd;padding:18px 0}}
.story:first-child{{border-top:0}}
.story-head{{display:flex;justify-content:space-between;gap:10px}}
.story-head h3{{margin:0;font-size:1.25rem}}
.move{{font-size:1.45rem;font-weight:800}}
.prediction{{background:#f3f4f5;border-left:4px solid #222;padding:10px 12px}}
.caution,.muted,small{{color:#666;font-size:.88rem}}
nav{{display:flex;gap:12px;flex-wrap:wrap}}
nav a{{font-weight:700}}
@media(max-width:700px){{
 .weather,.focuses{{grid-template-columns:1fr}}
 .paper{{padding:14px}}
 .mast h1{{font-size:1.6rem}}
}}
</style>
</head>
<body><main>
<div class='mast'>
  <h1>市場農場 朝刊</h1>
  <p>{now.strftime('%Y年%m月%d日')}｜初心者向け・読むだけ版</p>
</div>

<section class='paper'>
<p class='lead'>今日ここだけ読む：世界の空気 → 大きく動いたもの → 次に見る条件</p>
<p>研究用の数字はできるだけ隠しています。<b>「何が起きた？」「なぜかもしれない？」「次に何を見ればいい？」</b>の順で読めばOKです。</p>
<nav><a href='./index.html'>研究用の市場農場を見る</a></nav>
</section>

<section class='paper'>
<h2>今日の世界を4行で</h2>
<div class='weather'>
  <div><b>投資家の気分</b><br>{escape(mood)}</div>
  <div><b>ドル</b><br>{escape(dollar)}</div>
  <div><b>原油</b><br>{escape(oil_txt)}</div>
  <div><b>日本株</b><br>{escape(japan)}</div>
</div>
</section>

<section class='paper'>
<h2>今日、予測器が気にしている3つ</h2>
<p class='muted'>おすすめではありません。「上か下かの偏りが比較的大きいもの」です。</p>
<div class='focuses'>{''.join(focus_html)}</div>
</section>

<section class='paper'>
<h2>今日の「なぜ動いた？」</h2>
{''.join(stories)}
</section>

<section class='paper'>
<h2>この新聞の読み方</h2>
<p><b>1.</b> まず世界の4行だけ読む。<br>
<b>2.</b> 気になる銘柄の「何が起きた？」を見る。<br>
<b>3.</b> 「次に何を見ればいい？」を一つ覚える。<br>
<b>4.</b> 翌日、その条件が本当に起きたかを見る。</p>
<p class='caution'>この朝刊は投資助言ではなく、市場の因果関係を学ぶための観察ノートです。価格変動の原因は複数あり、ニュースと値動きの同時発生だけで因果を断定しません。</p>
</section>

</main></body></html>"""

    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")


def main():
    from .engine import load_config, analyze
    cfg = load_config()
    regime, results = analyze(cfg)
    render_newspaper(cfg, regime, results)
    print("newspaper generated")


if __name__ == "__main__":
    main()
