第三者ライブラリ（バンドラ・パッケージマネージャ不要のもの）をそのまま
置くディレクトリです。1ライブラリ1フォルダで、配布版ファイルをそのまま
コピーします（wikiSystem側では中身を書き換えません）。

URLは /.vendor/<フォルダ名>/<ファイル名> で配信されます
（wikilib.vendor.serve_vendor_asset、wiki.pyのdispatch参照）。

## diffmerge

2文書・3文書の比較・マージを行うブラウザツール。開発は別リポジトリ
（ClaudeWS/diffmerge、GitHub: yoshiyano/diff-merge_3way）。

  diffmerge/diffmerge.umd.js   配布版（UMD。<script>で読み込むとwindow.DiffMergeが生える）
  diffmerge/diffmerge.css      差分ビュー本体のスタイル

更新するときは、ClaudeWS/diffmerge 側で `python3 build.py` を実行して
dist/ を最新化し、dist/diffmerge.umd.js・dist/diffmerge.css をここへ
上書きコピーするだけです（このディレクトリでビルドはしません）。

使いかた（公開API・組み込み方法）は ClaudeWS/diffmerge のWiki
（このwikiSystemでは /=diffmerge3/ ファーム）を参照してください。
wikiSystem側の呼び出しコード（バックアップ画面など）は各機能のディレクトリ
（例: _sys/backupui/backup.js）にあります。

置き場所を用意する側（呼び出し側のCSS）は、**自前で overflow を持たない**
ようにしてください。`viewH: 'auto'`（既定）のdiffmergeは、高さを与える
flex/grid の中に置かれるとその高さいっぱいに広がり、内側だけを
スクロールさせて見出し行を固定します。外側にも overflow があると二重に
スクロールが出て、見出しの固定も効きません（_sys/backupui/backup.css の
`.bk-restore-view` を参照）。

同じ理由で、`table`・`th`・`td`に対する打ち消しCSSも当てないでください。
diffmerge.css は行の背景色や余白を td 側に持っているため、まとめて
打ち消すと差分の色分けが消えます。

## katex

LaTeX形式の数式をブラウザで組版する表示ライブラリ（KaTeX 0.16.11）。
plugin/katex.py（wikiPluginの持ち物）が使います。以前はCDNから読んで
いましたが、**手元に置く**ようにしました（Wiki設計者の指示、2026-09-02）。

  katex/katex.min.css   スタイル。fonts/ を相対パスで参照する
  katex/katex.min.js    本体（<script>で読み込むとwindow.katexが生える）
  katex/fonts/          数式用のフォント60個（20書体 × woff2/woff/ttf）

npmの配布物（katex@0.16.11）の dist/ 配下をそのままコピーしたものです。
更新するときも同じで、次のようにして dist/ の中身を丸ごと置き換えます
（このディレクトリでビルドはしません）。

  curl -sSLo katex.tgz https://registry.npmjs.org/katex/-/katex-<版>.tgz
  tar xzf katex.tgz package/dist/katex.min.css package/dist/katex.min.js \
      package/dist/fonts
  rm -rf katex && cp -r package/dist katex

**fonts/ は3種類とも置いてあります。** katex.min.css の @font-face が
woff2・woff・ttf の順に並べており、いまのブラウザは先頭のwoff2しか
取りに行きません（woff2だけなら296KB、3種類で1.2MB）。それでも減らして
いないのは、配布物をそのままの形で置く、というこのディレクトリの決まりに
合わせるためです。参照先が欠けた配布物にはしません。

auto-render拡張（contrib/auto-render.min.js）は使っていないので置いて
いません。数式の入れ物は plugin/katex.js が自分で見つけて描画します。
