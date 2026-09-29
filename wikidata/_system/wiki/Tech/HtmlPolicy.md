# 本文に書くHTMLの扱い

#code()

本文に書かれた生のHTMLを、どこまで通すかの決まりです（`_sys/wikilib/htmlpolicy.py`）。

## 3つの設定

記法ごとに決められます。**どちらも既定は `false`（通さない）**です。

| 設定 | 対象 |
|---|---|
| `markdown.allow_html` | `.md` のページ |
| `pukiwiki.allow_html` | `.txt` のページ |

| 値 | 書いたHTMLの扱い |
|---|---|
| `false`（既定） | **一切通しません。** タグごと文字として表示されます |
| `true` | **許可したタグ・属性だけ**通します。危ないものは文字になります |
| `all` | **すべて通します** |

#note(type=warn){{
2026-09-02より前は `markdown.allow_html: true` が「すべて通す」の意味でした。
同じ動きにしたい場合は `all` と書きます。
}}

## なぜ既定を変えたのか

素通しは保存型XSSになるためです。2026-09-02までは、本文の `<script>` や
`<img src=x onerror=…>` がそのまま出力され、編集できる人なら、開いた全員のブラウザで
スクリプトを動かせました。

## `true` のとき、何が通って何が止まるか

**XSSに関わりうるものは落とし、関わらないものは通します**（Wiki設計者の判断、
2026-09-02）。落とすものは、一般的なサニタイザ（GitHubのMarkdown描画・DOMPurifyの既定）に揃えてあります。

### 通すもの

- **表示のためのタグ** … 見出し・段落・リスト・表・引用・強調・
  `code`/`pre`・`details`/`summary`・`div`/`span`・`a`/`img`・ルビ など
- **どのタグにも付けてよい属性** … `class` `id` `title` `lang` `dir`
- **タグごとの属性** … `a` の `href`/`target`/`rel`、`img` の
  `src`/`alt`/`width`/`height`、`td`/`th` の `colspan`/`rowspan` など

`class` と `id` は、単体ではXSSに関わらないので通します。

### 止めるもの

| 何を | なぜ |
|---|---|
| `script` | そのまま任意のコードが動く |
| `style`要素・`style`属性 | **スクリプトが無くても実害を出せる**（下記） |
| `iframe` `object` `embed` | 外部の中身を埋め込める |
| `link` `meta` `base` | ページ全体の読み込み先・解釈を変えられる |
| `form` `input` `button` `textarea` `select` | 偽の入力欄で認証情報を集められる |
| `on…` で始まる属性 | `onclick` `onerror` などから任意のコードが動く |
| `href`/`src` の `javascript:` `data:` など | リンクや画像からコードが動く。通すのは `http` `https` `mailto` `ftp` `tel` と相対URLだけ |
| 宣言・CDATA | 中身を隠せる |

コメント `<!-- … -->` は、Markdown記法ではこの判定より前に**取り除きます**
（`wikilib.mdcomment`）。配信するHTMLに中身が残らないので、隠す手段にはなりません。

`style` は、CSSだけでも、編集ボタンの上に別の要素を重ねる、偽の入力欄に見せる、
属性セレクタと `background:url()` で入力内容を外へ送る、といったことができるので止めます。
本文の `<style>` はページ全体にも効きます。

飾るだけなら [プラグイン](/Syntax/Plugin/color)（`&color()` `&size()`）が設定に関わらず使えます。
HTMLをそのまま書きたい箇所は [`#html`](/Syntax/Plugin/html) で囲めます（既定は `true` と同じ水準、
`#html(all)` ならすべて通します）。

### 止めたものは、消さずに文字にします

許可されなかったタグは取り除かず、`&lt;script&gt;` のように文字として表示します。
消すと、書いた本人に何が起きたのか分からないためです。

## プラグインの出力は、この決まりの外です

**プラグインが返したHTMLは、設定に関わらずそのまま出ます。**
`&color()` の `<span style="color:red">` や `#note()` の `<div class="note…">`、
`#comment` の入力欄は、`false` にしても消えません。

プラグインは管理者が入れるコードで、編集者が本文に書くものとは信頼の度合いが違うためです。
プラグインの戻り値はパーサーを通りません（`plugins.call_plugin`）。

一方、プラグインが受け取る中身（body）は、編集者が書いたものなので本文と同じ扱いです。

```pukiwiki
#note(type=tip){<script>alert(1)</script>}
```

と書いても、`<script>` は文字になります。

中身はプラグインへ渡す前に展開し、戻り値は再パースしません（展開の宣言は
[PLUGIN_INFO の入れ子](/Tech/dev_plugin/plugin_info#入れ子expand_)）。2026-09-02より前は戻り値を
まるごとパースし直していたため、HTMLを通すと中身のHTMLまで生き、止めるとプラグインの外枠まで
文字になって壊れていました。

## プラグインは、自分が渡すテキストの水準を決められる

`allow_html` は **wikiSystemが自分でparseするときの最大権限**で、プラグインからの要求は縛りません
（Wiki設計者の判断、2026-09-02）。プラグインはどのみち戻り値でどんなHTMLでも出せるためです。
プラグインは、中身を展開させるときの水準を自分で選べます。

```python
PLUGIN_INFO = {
    "expand_inline": True,
    "body_html": "all",      # ページの設定が false でも、中身のHTMLは通す
}
```

`None`（既定）はページの設定に従い、`False` / `True` / `"all"` はページの設定に関わらずその水準に
なります（[PLUGIN_INFO](/Tech/dev_plugin/plugin_info#中身のhtmlをどこまで通すかbody_html)）。
