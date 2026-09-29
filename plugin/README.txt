全 wiki 共通のプラグインを配置するディレクトリです。
各wiki固有のプラグインは wikidata/<farm名>/plugin/ に配置します。

同じ名前のプラグインが両方にある場合、farm固有のものが共通のものを上書きします
（farmの設定が共通の設定を上書きする、というシステム全体の考えかたに揃えています）。

"." や "_" で始まるファイルは読み込まれません。編集中の一時ファイルや、
プラグインから共有したいモジュールの置き場所として使えます。

## プラグインの書きかた

1つのPythonファイルが1つのプラグインで、ファイル名がプラグイン名になります。
必要な関数だけを定義します。

    PLUGIN_INFO = {"help": "書きかた: #hello(name=世界)"}

    def _setup(ctx):                          # リクエストごとに1回
        ...

    def _convert(args, kwargs, body, ctx):    # #hello(...) から呼ばれる
        return "<p>こんにちは</p>"

    def _inline(args, kwargs, body, ctx):     # &hello(...); から呼ばれる
        return "<span>こんにちは</span>"

    def _action(ctx):                         # /.plugin/hello から呼ばれる
        return "<p>API等に使えます</p>"

_convert / _inline は HTML文字列を返します。

## 同梱しているサンプル

note.py     … ブロック・インライン両対応。入れ子（expand_*）を受け入れる例
contents.py … ページ全体の見出しが必要な例（whole_page を宣言）
tasklist.py … 旧来の register(md) 形式（markdown-it-py を直接拡張する）

## code.css / code.js — Prism.jsによるシンタックスハイライト

`code.py`（#codeプラグイン）が実際に使われたページでだけ、この2ファイルが
自動で読み込まれる（`context.used_plugins`に"code"が入ったページに限り、
`_sys/wikilib/plugins.py`の`plugin_asset_urls`が`<link>`/`<script>`を
足す既存の仕組み。他のプラグインのCSS/JSと扱いは同じ）。

中身はPrism.js本体（テーマ`prism`、言語47種、プラグイン11種）。ソースの
取得・連結は`theme/prism.build.py`が行う（標準ライブラリのみ・実行可、
Git管理対象。バージョンを上げる・言語やプラグインを増減するときは、
このスクリプト内の定数を直して再実行すればよい）。以前はテーマ側で
全ページ無条件に読み込んでいたが、`#code`を使わないページにまで
150KB超を配る無駄があったため、2026-08-29にこの仕組みへ移した。

対象は`<pre><code class="language-xxx">...</code></pre>`（Markdownの
コードフェンスが生成するのと同じ形のHTML）。

**Markdown記法（.md）のページは、`#code`の使用有無に関わらず無条件で
この資材が読み込まれる**（`_sys/wikilib/themes.py`の`render_with_theme`、
2026-08-29追加）。素のコードフェンスが`#code`を経由せず色付け対象になる
以上、`used_plugins`ベースの絞り込みとは相性が悪い（絞り込んだままだと
フェンスしか使わないページで永遠にPrismが読み込まれない）ための例外。

**PukiWiki記法（.txt）のページはコードブロックが`#code`経由でしか
作れないため、今までどおり`used_plugins`ベース**（実際に`#code`が
呼ばれたページでだけ読み込まれる）。中身無しの`#code()`は、PukiWiki
記法のページで色付けだけ有効にしたいときの合図として引き続き使える
（読み込みの合図としてだけ働き、何も表示しない。`code.py`側の仕様）。

### プラグイン側からPrismの機能を制御する決まりごと

`#code`をはじめ、`<pre><code class="language-xxx">`を出すプラグインは、
**Prism自身の属性・クラス名の規約にそのまま従う**ことで、行番号や行の
ハイライトなどを個別に効かせられる。中間層は新設していない（新しい
Prismプラグインを足したときも、この一覧を増やすだけでよい）。

  行番号は既定でON        個別に消したいときだけ`<pre>`に
                        `class="no-line-numbers"` を足す（Prism本体の
                        `Prism.util.isActive()`が祖先を`<html>`まで遡って
                        判定する仕組みを使い、`<html>`側に`class="line-numbers"`
                        を付けて全体の既定をONにしてある。個別の`<pre>`に
                        `no-line-numbers`を付ければ、祖先を遡る途中で
                        先に見つかり既定より優先される。2026-08-29に
                        既定OFF→既定ONへ変更。#codeの`nonum`はこの
                        `no-line-numbers`クラスの付与に対応すること）
  特定の行をハイライト   `<pre>`に `data-line="4,7-10"` を足す（行番号、
                        カンマ区切り・ハイフンで範囲指定）
  コマンドライン風表示   `<pre>`に `class="command-line"` を足し、
                        必要に応じて `data-user`/`data-host`/`data-prompt`/
                        `data-output`（出力行の行番号、`data-line`と同じ書式）
                        `data-filter-output`（出力行を示す行頭記号の正規表現）
                        を足す
  タブ・空白・改行の可視化 `<pre>`に `class="show-invisibles"` を足す
                        （Prism本体は既定で全コードブロックに常時効く仕様だが、
                        読み物としては主張が強すぎるとの指摘を受け、
                        `pre.show-invisibles`配下だけに効くようwikiSystem側で
                        CSSをスコープしてある。prism.build.pyのSCOPED_PLUGIN_CSS
                        参照。JS側のトークン付与自体は元のまま全コードブロックに
                        入るので、あとからクラスを足すだけで見えるようになる）
  コピーボタンの個別非表示 `<pre>`に `data-no-copy` を足す（Prism標準の
                        属性ではなく、wikiSystem側がCSSだけで実現した
                        独自の仕組み。copy-to-clipboardにはブロック単位で
                        自身を止めるAPIが元から無いため、toolbarが作る
                        DOM構造を利用してCSSの一般兄弟結合子で個別に隠して
                        いる。prism.build.pyのNO_COPY_CSS参照）

  以下は個別のON/OFF不要、読み込まれたページの全コードブロックに自動で効く:
    - ツールバー・コピー・使用言語の表示（toolbar/copy-to-clipboard/show-language）
    - キーワード別クラス付与（highlight-keywords。今のところそれを狙った
      CSSは書いていないので見た目上の変化は無い）
    - 貼り付けたマークアップの保持（keep-markup。中身のHTMLが元から
      プレーンテキストしか持たない`#code`では今のところ無関係）

  `language-xxx`の`xxx`が上の言語一覧に無い場合、autoloaderが該当言語だけを
  jsdelivr（このビルドと同じバージョン）からその場で取得しようとする
  （`code.js`自身に`Prism.plugins.autoloader.languages_path`を設定する
  形で組み込み済み。閲覧者のブラウザからCDNへの通信になるので、届かない
  環境では単に色が付かないだけでエラーにはならない）。

## エラーの扱い

プラグインの不備は、そのプラグインを使っている箇所だけのエラー表示になります。
読み込みに失敗しても例外を投げても、ページの他の部分や他のプラグインには影響しません。
config/default.yaml で debug: true にする（または --debug で起動する）と、
エラーの詳細が折りたたみで表示されます。

詳しい説明は wiki ページ /PluginGuide（一般向け）と /Tech/PluginGuide（開発者向け）を
参照してください。
