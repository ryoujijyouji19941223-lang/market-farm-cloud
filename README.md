# 市場農場 Cloud v0.2

PCをつけっぱなしにせず、GitHub Actionsが日本時間の朝8時台・夜8時台に自動実行し、GitHub Pagesのダッシュボードを更新する試作です。

## 何をするか

- 朝: その日の方向を予測して記録
- 夜: 最新価格で答え合わせ用データを保存
- 予測精度を銘柄ごとに累積
- スマホでGitHub Pagesを見る

> GitHub Actionsのscheduleは混雑時に数分〜数十分遅れることがあります。秒単位・分単位のトレード用途ではありません。

## 対象

ドル円 / ユーロ円 / スイスフラン円 / 金 / 任天堂 / 三井住友FG / キオクシア / サンリオ / 日本製鉄 / アスタリスク / オーテック / KLab

## センサー v0.2

- 個別価格トレンド
- 5日モメンタム
- ボラティリティ
- 簡易ニュース
- 原油
- VIX
- S&P 500
- 日経平均
- 米10年金利
- ドル指数

次版では中央銀行イベント、CFTC大口ポジション、ETF資金流、SNS急増検知、仮想10万円ポートフォリオを追加予定。

## 現在のクラウド構成

- GitHub Actions: 分析エンジン。PCがOFFでも実行される。
- `data/state.json`: 予測・結果・的中率の履歴。
- `docs/index.html`: スマホ表示用ダッシュボード。
- GitHub Pages: `docs/index.html` をWeb公開する役目。

## GitHub Pagesについて

GitHub FreeではPagesを使うリポジトリをPublicにする必要があります。GitHub Pro等ではPrivateリポジトリでもPagesを利用できますが、Pagesサイト自体は公開URLになります。

この試作にはAPIキーや個人情報を保存しない設計です。Public化したくない場合は、分析エンジンをPrivateのまま運転し、将来的に認証付きの別ホストへダッシュボードだけ移す構成が適しています。

## Pagesを有効にする一度だけの操作

1. GitHub Freeで使う場合: Settings → General → Danger Zone → Change repository visibility → Public。
2. Settings → Pages → Source を **GitHub Actions** にする。
3. Pages workflowが成功するとスマホ用URLが発行される。

分析本体はPagesが無効でも動作します。

## 時刻

GitHub ActionsのcronをUTCで指定し、日本時間の平日 08:07 と 20:07 に実行します。毎時00分は混雑で遅延しやすいため、7分ずらしています。土日は市場休場による誤採点を避けるため自動実行しません。

## 注意

- yfinanceは無料で便利ですが公式市場データAPIではないため、長期運用では正式なデータ源に交換した方が堅牢です。
- ニュース感情判定はv0.2では簡易版です。
- 表示される「上昇スコア」は投資助言でも、統計的に校正済みの真の確率でもありません。蓄積した実績で校正します。
