"""pre — 中身をそのまま整形済みテキスト（<pre>）として表示する、ブロック専用のプラグイン。

    #pre(){{
    複数行の内容を
    そのまま表示します
    }}
    #pre(copy){print("hello")}
    #pre(color=#223344){背景色つき}
    #pre(verb){**強調**や&note();も展開されます}

このシステム独自のプラグインです（本家PukiWikiには同名のプラグインは
ありません）。スペースで文頭を字下げする整形済みテキスト（本家のPre）と
同じ見た目・同じ`<pre>`表示になりますが、行頭にスペースを置く必要は
ありません。

 1. verb  … 中身をインライン記法・インラインプラグインとして展開するか
       (default: 展開しない＝書いたとおりの文字がそのまま表示されます)
       trueにすると、`**太字**`や`&note();`のようなインライン記法が
       解釈されます（詳しくは技術資料）
 2. copy  … 右上に「COPY」ボタンを出すか (default: 出さない)
       押すと中身（書いたとおりの生テキスト）をクリップボードへコピーします
 3. color … 枠の背景色。`#RGB`または`#RRGGBB`の形で指定します (default: 指定なし＝テーマの既定色)

`verb`・`copy`はどちらも単語を書くだけで有効になる真偽オプションです
（`#pre(verb, copy){...}`のように好きな順で組み合わせられます）。
"""

""" 技術資料
本家PukiWikiに同名のプラグインは無いため、後方互換の制約を受けない
（`../CLAUDE.md`のPukiWiki互換方針は移植プラグインだけが対象）。

## verb（インライン展開）と expand_* の静的な制約

このプラグインは「既定では中身を一切解釈しない（コード表示用）」が、
`verb`を指定すると「中身をインライン記法・インラインプラグインとして
解釈する」という、**同じ呼び出し方（ブロック）の中で引数の値に応じて
展開の有無を切り替えたい**プラグインである。

`PLUGIN_INFO`の`expand_inline`/`expand_plugin`はプラグイン単位で静的に
決まり、`resolved`（そのときの引数値）を見て呼び出しごとに切り替える
ことはできない（詳しくは`../SPECIFICATIONS.md`の「5. expand_*」参照）。
そのため、このプラグインは`expand_*`をいずれも宣言せず（常にFalse）、
`verb`が真のときだけ`_convert`の中から`wikilib.plugins.build_expand_renderer`・
`wikilib.plugins.expand_pukiwiki_output`・`wikilib.render.is_pukiwiki`を
直接呼び、フレームワークが`expand_body()`の中で行っているのと
同じ処理を自前で行う（`_expand_verbatim`）。

`depth`（入れ子の深さ、多重再帰防止の上限に使う値）は`_convert`には
渡されないため`0`を使う。このプラグイン自身が既に深い入れ子の中で
呼ばれている状況までは、多重再帰の安全装置が追随しない（既知の軽微な
制限。`#pre`が他のプラグインの展開結果として呼ばれる状況は稀なため、
実害は小さいと判断した）。

`expand_block`は展開しない（`verb`はあくまで「インライン記法の展開」で
あり、`<pre>`の中に段落・見出し・リストが増えるのは望ましくないため）。

## verb=false の出力が `<pre><code>...</code></pre>` である理由

スペースで字下げする整形済みテキスト（本家のPre、`_PreNode`）と同じ
markdown-it-pyの既定`code_block`レンダー規則の出力（`<pre><code>escaped
</code></pre>`、中身の末尾に改行を1つ添える）に合わせた。`verb=true`の
場合は中身が実際のHTML（リンク・強調タグ等）を含みうるため、「コード」を
意味する`<code>`タグでは包まず`<pre>{展開結果}</pre>`とする。

## `<pre>`に`.pre-body`クラスを足している理由（テーマCSSとの詳細度の衝突）

Wiki設計者から「`color`（背景色のはず）が、実際には塗られず細い枠線だけ
色が付いて見える」と報告を受けて調査した。`base.css`/`bloom.css`は
行頭スペースの整形済みテキスト等、素の`<pre>`向けに`.content pre {
background: var(--code-bg); border: 1px solid var(--border); ... }`という
汎用ルールを持っている。このプラグインが出力する`<pre>`もこれに拾われて
しまい、詳細度が旧`.pre-box pre`（class1つ＋要素1つ）と**同点**だった
ため、「プラグインCSS→テーマCSSの順で読み込み、衝突時はテーマが勝つ」
という規約（`Tech/dev_plugin#cssは基本的にプラグイン自身が持つ`）どおり
テーマ側が勝っていた。結果、内側の`<pre>`が不透明な背景と自前の枠線を
持ってしまい、外側`.pre-box`の`background-color`（`color`引数の値）を
完全に覆い隠し、枠線も二重になっていた。

`<pre>`に`pre-body`クラスを足し、CSS側を`.pre-box .pre-body`
（class2つ）にすることで、テーマの`.content pre`（class1つ＋要素1つ）
より詳細度を確実に上回らせ、読み込み順に関わらず勝つようにした
（`background: none; border: none;`で内側の背景・枠線を明示的に消し、
`.pre-box`側だけに色・枠線を持たせる）。副次効果として、テーマごとに
違う`.content pre`の`padding`（base: `0.8rem 1rem`、bloom: `1rem
1.2rem`）に左右されず、どのテーマでも同じ余白になった。

## copy でコピーする内容

表示上の見た目（`verb=true`で展開された結果）ではなく、**書いたとおりの
生テキスト**（`body`そのもの）をコピー対象にする。`_sys/editor/editor.js`
の「コピー」ボタン（`data-ref`に書きかたを持たせる方式）と同じ考えかたで、
ボタン要素の`data-pre-copy`属性に生テキストを載せておき、`pre.js`側は
その属性だけを読む（表示側にリンク等のHTMLタグが混ざっていても、
コピーされる内容は常に書いたとおりの文字列になる）。

## color の検証（`candidate`宣言だけでは足りない）

`#RGB`（3桁）・`#RRGGBB`（6桁）の16進（先頭に`#`必須）だけを許可する
（2026-08-27、Wiki設計者の指示で3桁も追加。全プラグインで統一する方針の一環）。
`color.py`と違い、色名・4桁（`#RGBA`）・8桁（`#RRGGBBAA`）は受け付けない
（`color`引数はユーザー指定で`#RRGGBB`限定という当初の仕様のうち、
桁数だけを`color.py`に揃えた形。アルファつきの短縮形・色名までは
今回の指示の範囲外と判断し、追加していない）。値をそのまま
`style="background-color:..."`へ埋め込むため、CSSインジェクションを
防ぐ検証が要る。

**`args`の`candidate`宣言だけでは、いまも位置引数側の検証が抜ける。**
開発時点（2026-08-26）では`num_order: -1`（残りの位置引数の受け皿）の
項目は、キーワード指定（`color=...`）でも位置引数の連結でも`candidate`
が一切適用されない不具合があった（`_bind_free_order_args_impl`が
`resolved[name] = raw`／`",".join(leftover)`をそのまま使うだけで、他の
項目のような`_resolve_arg_value`を経由しなかったため）。実際に
`#pre(color=red;background:url(x)){x}`のような値がそのまま`style`属性に
埋め込まれることを`build_markdown_renderer`で確認し、wikiSystem側へ
報告した。

**2026-08-27、キーワード指定の経路だけ修正された**（`Tech/dev_plugin/spec`
に明記済み）。**位置引数の連結経路は、複数の値をまとめた文字列になり
単一値の`candidate`とは意味が合わないという判断で、意図的に無検証の
まま**（`#pre(red){x}`のような書きかたは依然として`candidate`を通らない）。
そのため`_convert`の中で`COLOR_RE.fullmatch()`による**自前の**再検証は
修正後も外していない（`PLUGIN_INFO`の`candidate`宣言は、キーワード
指定時にフレームワークが検証してくれるようになった今も、通常の呼び出し
例のエラーメッセージ用途と、位置引数側の抜け穴に対する安全網を兼ねる）。

## 引数の自由順序化

`verb`/`copy`はどちらも`num_order`を宣言しない自由順序の`flag`項目。
`color`だけ`num_order: -1`（残りの位置引数の受け皿）を持たせ、これを
自由順序モードへの切り替えの足場にしている（`args`全体を自由順序に
するには最低1項目の`num_order`宣言が要る。詳しくは
`../SPECIFICATIONS.md`の「4. num_order」参照）。`verb`/`copy`のどちらも
「常に必須の1番目」のような固定位置を持たない対等なオプションなので、
固定位置（正の`num_order`）ではなく`-1`の受け皿役を選んだ。
"""

from wikilib.plugins import (
    PluginArgumentError,
    build_expand_renderer,
    expand_pukiwiki_output,
)
from wikilib.render import is_pukiwiki
from html import escape
import re

COLOR_RE = re.compile(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}")
COLOR_PATTERN = (COLOR_RE.pattern, "re")

PLUGIN_INFO = {
    "help": "#pre(verb,copy,color){中身}",
    "args": [
        {"name": "verb", "flag": True, "default": False, "label": "インライン展開"},
        {"name": "copy", "flag": True, "default": False, "label": "コピー"},
        {"name": "color", "num_order": -1, "candidate": [COLOR_PATTERN], "default": None, "label": "背景色"},
    ],
}


def _expand_verbatim(body, context):
    """`body`をインライン記法・インラインプラグインとして展開する（verb用）。

    フレームワークの`expand_body()`が`expand_inline`+
    `expand_plugin`宣言時に行うのと同じ処理を、静的な宣言に頼らず
    その場で行う（詳しくは技術資料）。"""
    info = {"expand_inline": True, "expand_plugin": True, "expand_block": False}
    engine = build_expand_renderer(context, info, 0)
    env = {"wiki": context}
    if is_pukiwiki(getattr(context, "ext", ".md")):
        return expand_pukiwiki_output(body, engine, context, False, env)
    return engine.renderInline(body, env)


def _convert(resolved, body, context):
    if not body:
        raise PluginArgumentError(
            "表示する内容を指定してください: #pre(){{ 内容 }}"
        )

    color = resolved["color"]
    if color and not COLOR_RE.fullmatch(color):
        raise PluginArgumentError(
            f"背景色は #RGB または #RRGGBB の形で指定してください: {color}"
        )
    box_attr = f' style="background-color:{color}"' if color else ""

    button = ""
    if resolved["copy"]:
        button = f'<button type="button" class="pre-copy" data-pre-copy="{escape(body, quote=True)}">COPY</button>\n'

    if resolved["verb"]:
        inner = f'<pre class="pre-body">{_expand_verbatim(body, context)}</pre>'
    else:
        inner = f'<pre class="pre-body"><code>{escape(body)}\n</code></pre>'

    return f'<div class="pre-box"{box_attr}>\n{button}{inner}\n</div>\n'
