"""blockdiv — 枠つきの箱（div）を作り、段組みや回り込みに使うブロック専用のプラグイン。

    #blockdiv(float:left,bordercolor:transparent,width:48%,margin:2px)
    左の段の中身
    #blockdiv(end)
    #blockdiv(float:right,bordercolor:transparent,width:48%,margin:2px)
    右の段の中身
    #blockdiv(end)
    #clear()

    #blockdiv(width=48%, bordercolor=transparent, margin=2px){{
    中身を {{ }} で囲むと、#blockdiv(end) を書かなくても閉じます
    }}
    #blockdiv(float=none, border="dashed 2px #0064c8", radius=8px, padding=1em){{
    回り込ませない、角の丸い点線の箱
    }}

指定は `名前=値`（新しい書きかた）でも、`名前:値`（PukiWikiでの書きかた）でも
書けます。どちらも好きな順で、書きたいものだけ書けます。

 1. end         … 単語を書くと、前の `#blockdiv(...)` で開いた箱を閉じる
 2. float       … 回り込み。left / right / none (default: left)
 3. clear       … 回り込みを止める。left / right / both / none (default: 止めない)
       書くと、ほかの指定は使われず「回り込みを止めるだけの箱」になります
 4. width       … 幅 (default: auto＝中身に合わせる)
 5. align       … 文字の寄せ。left / center / right / justify (default: left)
 6. border      … 枠線をまとめて「種類 太さ 色」の順で (default: solid 1px inherit)
       例: border="dashed 2px #0064c8"。書いた部分だけが下の3つを上書きします
 7. borderstyle … 枠線の種類。solid / dashed / dotted / double / none など (default: solid)
 8. borderwidth … 枠線の太さ (default: 1px)
 9. bordercolor … 枠線の色 (default: inherit＝外側から引き継ぐ。枠を消すなら transparent)
10. backcolor   … 背景色 (default: inherit)
11. margin      … 箱の外側の余白 (default: 0px)
12. padding     … 箱の内側の余白 (default: 0px)
13. class       … 箱に付けるclass名 (default: blockdiv)
       PukiWikiでの書きかたでは `style:名前` がこれに当たります
14. color       … 文字の色 (default: 指定しない)
15. radius      … 角の丸み (default: 丸めない)
16. css         … そのほかのCSSを「プロパティ:値;」の形でそのまま足す (default: 足さない)
       例: css="display:flex; gap:1em"
17. start       … 書いても何も変わりません（PukiWikiの書きかたとの互換のため）

`#blockdiv(...)` だけを書いた場合は、次の `#blockdiv(end)` までが箱の中身です
（PukiWikiと同じ書きかた）。`#blockdiv(...){{ ... }}` と中身を囲んだ場合は、
その場で閉じるので `#blockdiv(end)` は要りません。

左右に並べた箱の後ろには `#clear()` を置いて回り込みを止めてください。
値に `,` を含めたいとき（`rgb(0,100,200)` など）は、`名前="値"` と引用符で
囲んで書きます。

エラーになる書きかた:

- 知らない名前（`名前:値`・単語どちらも）を書いた
- 値に使えない文字（`;` `:` `"` `<` `>` `{` `}` `\\` など）を含めた
- `css` に `url(` や `\\` を含めた
- `end` と `{{ }}` の中身を同時に書いた
"""

""" 技術資料
本家には無い自作プラグイン（pukiwiki.osdn.jp「自作プラグイン/blockdiv.inc.php」）で、
手元の `~/pukiwiki/.wkcommon/plugin/blockdiv.inc.php` を読んで移植した。本家の
仕様と、それをどう残したか:

- 引数は `名前:値`（`/^ *([a-zA-Z0-9_]+):([a-zA-Z0-9%_# ]+)$/`）か単語
  （`/^ *([a-zA-Z0-9_]+) *$/` → その名前を true）の並び。名前は小文字化。
  → 位置引数の受け皿（`num_order: -1` の `legacy`）で丸ごと受け取り、
  `_parse_legacy` で自前に読む。名前の大文字小文字は本家どおり区別しない。
  `名前=値` の新しい書きかたは同じ名前を `kw_only` で宣言して受ける
  （`kw_only` にしないと、自由順序の項目が `float:left` のような位置引数を
  先取りしてしまう。`kw_only` は2026-09時点で SPECIFICATIONS.md に未記載だった
  ため追記した）。両方に同じ名前を書いたら `名前=値` を優先する。
- 本家は値が正規表現に合わない引数・知らない名前を**黙って捨てていた**。
  ここでは wikiSystem 全体の「宣言に無い引数はエラー」の方針に合わせて
  エラーにした。2026-09-25 に `~/pukiwiki/*/wiki/*.txt`（現行ページ）を
  調べた範囲では、使われていた名前は float / bordercolor / width / margin と
  end だけで、すべてこの検証を通る（壊れるページは無い）。
- 既定値（float:left、1px solid inherit の枠、背景 inherit、margin/padding 0）と、
  既定値も含めて全部を style に書き出す出力の形は本家のまま。枠の色の既定
  `inherit` は外側の border-color（ふつうは文字色）を引き継ぐので、何も
  書かないと文字色の枠が付く。実ページのほとんどが `bordercolor:transparent`
  を書いているのはこのため。
- `border` の一括指定は、個別の指定より後に空白で割って上書きする（本家の
  処理順どおり。`border:solid 1px gray` 形式）。
- `clear` を書いたら `style="clear:…;"` だけの箱になり、ほかの指定は捨てる
  （本家の分岐のまま。`#blockdiv(clear:both)` 〜 `#blockdiv(end)` という使いかた）。
- `end` は `</div>` を返すだけ。本家は `$params['end']` を未定義のまま比べる
  （PHPの警告を無視する前提）作りだった。

## 開いたまま・閉じすぎ

`#blockdiv(...)` 単独の形は、開きタグと閉じタグを別々のプラグイン呼び出しが
返す（本家と同じ）。返したHTMLは再パースされないので、ブラウザが見るのは
`<div …>` → 本文 → `</div>` の並びそのままで、段組みは本家と同じに組める。
弱点も本家と同じで、

- `end` を書き忘れると、ブラウザは外側（テーマの本文領域）の `</div>` で
  この箱を閉じ、以降のレイアウトが1段ずれる。
- `end` が多すぎると、外側（テーマ）の `div` を閉じてしまう。

後者はページを壊すので、`context._blockdiv_depth`（ページごとの開いた数。
`comment.py` の `context._comment_counters` と同じ持ち回しかた）を数え、
開いていないのに来た `end` はエラー表示にして `</div>` を出さない。部分
プレビュー（`context.partial`）では開きが前の節にあるのが普通なので、
黙って空を返す。前者（閉じ忘れ）は描画の最後に呼ばれる口が無いので防げない。
**閉じ忘れの心配が無い `{{ }}` の形（本家に無い拡張）を新しく書くときの
既定の書きかたとして案内する。**

`{{ }}` の中身は `expand_block`/`expand_inline`/`expand_plugin` で展開済みの
HTMLとして届く（`note.py` と同じ）。中身の中にさらに `#blockdiv` を入れ子に
書ける。

## 値の検証

style 属性にそのまま入れるので、1つ1つの値は `VALUE_RE`（英数字と
`% # . - _ 空白 ( ) , / +`）だけに絞り、`;` で別のプロパティを足したり
属性から抜け出したりできないようにしている（本家の `[a-zA-Z0-9%_# ]+` より
少し広い。`48.5%`・`rgb(0,100,200)`・`calc(50% - 1em)` を通すため）。
`css` だけは複数のプロパティを書くための逃げ道なので `;` と `:` を許すが、
`url(`・`expression`・`\\`・`<`・`>`・`{`・`}`・`@`・`/*` は断る
（`allow_html` が許可なら `<div style>` を直接書けるので、表現力として
新しく開くものは無いが、外部資源の読み込みやCSSの構文崩しはこの口からは
させない）。最後に属性値として `html.escape` する。
"""

import re
from html import escape

from wikilib.plugins import PluginArgumentError

# 1つの値として style に入れてよい文字（`;` `:` `"` `<` などで抜け出させない）
VALUE_RE = re.compile(r"[A-Za-z0-9%#.\-_ (),/+]+")
# `css` 引数で断る並び
CSS_FORBIDDEN_RE = re.compile(r"url\(|expression|\\|[<>{}@]|/\*", re.IGNORECASE)
CLASS_RE = re.compile(r"-?[A-Za-z_][A-Za-z0-9_-]*(?:\s+-?[A-Za-z_][A-Za-z0-9_-]*)*")

# 名前 → (CSSプロパティ, 既定値)。既定値が None のものは書かれたときだけ出す。
# 並びは本家の出力順（float, width, text-align, border-*, background, margin, padding）
STYLE_PROPS = [
    ("float", "float", "left"),
    ("width", "width", "auto"),
    ("align", "text-align", "left"),
    ("borderstyle", "border-style", "solid"),
    ("borderwidth", "border-width", "1px"),
    ("bordercolor", "border-color", "inherit"),
    ("backcolor", "background-color", "inherit"),
    ("margin", "margin", "0px"),
    ("padding", "padding", "0px"),
    ("color", "color", None),
    ("radius", "border-radius", None),
]
FLOAT_VALUES = ["left", "right", "none"]
CLEAR_VALUES = ["left", "right", "both", "none"]
ALIGN_VALUES = ["left", "center", "right", "justify"]
# `名前:値`／`名前=値` のどちらでも書ける名前（`style` は `class` の旧名）
VALUE_NAMES = [name for name, _prop, _default in STYLE_PROPS] + ["clear", "border", "class", "css"]
LEGACY_ALIASES = {"style": "class"}
DEFAULT_CLASS = "blockdiv"

PLUGIN_INFO = {
    "help": "#blockdiv(float,width,border,bordercolor,backcolor,margin,padding,...){中身} / #blockdiv(end)",
    "expand_block": True,
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "end", "flag": True, "default": False},
        {"name": "start", "flag": True, "default": False},
        {"name": "float", "kw_only": True, "default": None, "candidate": FLOAT_VALUES},
        {"name": "clear", "kw_only": True, "default": None, "candidate": CLEAR_VALUES},
        {"name": "width", "kw_only": True, "default": None},
        {"name": "align", "kw_only": True, "default": None, "candidate": ALIGN_VALUES},
        {"name": "border", "kw_only": True, "default": None},
        {"name": "borderstyle", "kw_only": True, "default": None},
        {"name": "borderwidth", "kw_only": True, "default": None},
        {"name": "bordercolor", "kw_only": True, "default": None},
        {"name": "backcolor", "kw_only": True, "default": None},
        {"name": "margin", "kw_only": True, "default": None},
        {"name": "padding", "kw_only": True, "default": None},
        {"name": "class", "kw_only": True, "default": None},
        {"name": "color", "kw_only": True, "default": None},
        {"name": "radius", "kw_only": True, "default": None},
        {"name": "css", "kw_only": True, "default": None},
        # PukiWikiの `名前:値` の並び（どの項目にも当てはまらなかった位置引数）
        {"name": "legacy", "num_order": -1, "default": ""},
    ],
}


def _parse_legacy(text):
    """位置引数で書かれた `名前:値`／単語の並びを {名前: 値} にする（単語は True）。"""
    params = {}
    for token in (text or "").split(","):
        token = token.strip()
        if not token:
            continue
        name, sep, value = token.partition(":")
        name = name.strip().lower()
        name = LEGACY_ALIASES.get(name, name)
        if not sep:
            # `end`/`start` は flag 側が受け取るので、ここに来る単語は知らないもの
            raise PluginArgumentError(f"知らない指定です: {token}")
        if name not in VALUE_NAMES:
            raise PluginArgumentError(f"知らない指定です: {name}")
        params[name] = value.strip()
    return params


def _checked(name, value):
    """style に入れる1つの値を確かめる。候補のある名前は候補どおりに揃える。"""
    value = " ".join(str(value).split())
    if not value or not VALUE_RE.fullmatch(value):
        raise PluginArgumentError(f"{name}の値に使えない文字が含まれています: {value}")
    choices = {"float": FLOAT_VALUES, "clear": CLEAR_VALUES, "align": ALIGN_VALUES}.get(name)
    if choices and value.lower() not in choices:
        raise PluginArgumentError(f"{name}には {' / '.join(choices)} のどれかを指定してください: {value}")
    return value.lower() if choices else value


def _collect(resolved):
    """`名前:値`（位置引数）と `名前=値`（名前付き）を1つにまとめる。後者が優先。"""
    params = _parse_legacy(resolved.get("legacy"))
    for name in VALUE_NAMES:
        if resolved.get(name) not in (None, ""):
            params[name] = resolved[name]
    return params


def _open_tag(params):
    cls = params.get("class") or DEFAULT_CLASS
    cls = " ".join(str(cls).split())
    if not CLASS_RE.fullmatch(cls):
        raise PluginArgumentError(f"classの値に使えない文字が含まれています: {cls}")

    if params.get("clear"):
        # 本家どおり、clear を書いたら回り込みを止めるだけの箱にする
        return f'<div class="{escape(cls)}" style="clear:{escape(_checked("clear", params["clear"]))};">'

    values = {name: _checked(name, params[name]) for name in VALUE_NAMES
              if name not in ("clear", "class", "css", "border") and params.get(name)}
    if params.get("border"):
        # 「種類 太さ 色」の順に、書かれた部分だけ個別の指定を上書きする（本家どおり）
        parts = _checked("border", params["border"]).split(" ")
        for name, part in zip(("borderstyle", "borderwidth", "bordercolor"), parts):
            values[name] = part

    decls = []
    for name, prop, default in STYLE_PROPS:
        value = values.get(name, default)
        if value is not None:
            decls.append(f"{prop}:{value};")
    css = " ".join(str(params.get("css") or "").split())
    if css:
        if CSS_FORBIDDEN_RE.search(css):
            raise PluginArgumentError(f"cssに使えない書きかたが含まれています: {css}")
        decls.append(css if css.endswith(";") else css + ";")
    return f'<div class="{escape(cls)}" style="{escape(" ".join(decls))}">'


def _depths(context):
    """ページごとの「開いたまま」の数。1回の描画のあいだ context に乗せて持ち回す。"""
    depths = getattr(context, "_blockdiv_depth", None)
    if depths is None:
        depths = {}
        context._blockdiv_depth = depths
    return depths


def _convert(resolved, body, context):
    page = getattr(context, "page", "") or ""
    depths = _depths(context)

    if resolved["end"]:
        if body is not None:
            raise PluginArgumentError("end と中身（{{ }}）は同時に書けません。")
        if depths.get(page, 0) <= 0:
            if getattr(context, "partial", False):
                return ""
            raise PluginArgumentError("閉じる箱がありません（対応する #blockdiv(...) がありません）。")
        depths[page] -= 1
        return "</div>\n"

    tag = _open_tag(_collect(resolved))
    if body is None:
        depths[page] = depths.get(page, 0) + 1
        return tag + "\n"
    return f"{tag}\n{body}\n</div>\n"
