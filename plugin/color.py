"""color — 文字色・背景色を指定するインラインプラグイン。

    &color(fg=red){文字};                 文字色だけ
    &color(fg=red, bg=yellow){文字};      文字色と背景色
    &color(, yellow){文字};               背景色だけ（fgを飛ばす）

PukiWikiの `&color()` に合わせた書きかたです。`<font>` タグは使わず、
`<span style="color:...">` のような現行のCSSだけで色を付けます。

 1. fg … 文字色 (default: 色を付けない)
       red / crimson のような色名、#f00 / #ff0000 / #ff0000cc（アルファつき）
       のような16進が書けます。rgb() / hsl() のような丸括弧を使う関数表記は
       指定できません
 2. bg … 背景色 (default: 色を付けない)
       fgと同じ書きかたです

fg・bg は少なくとも一方を指定してください（両方省略はエラーになります）。
中身にはインライン記法（**太字**やリンクなど）が使えます。
&color(fg=red){**重要**な[リンク](/)}; のように書けます。
"""

""" 技術資料
fg/bg の検証は PLUGIN_INFO["args"] の candidate（COLOR_PATTERN の "re" 版）
で行っている。値をそのまま <span style="..."> のstyle属性へ埋め込むため、
書ける文字を16進（3/4/6/8桁）と色名だけに絞り、url() や ; の混入を防いでいる。

fg/bg には num_order（1・2）も明示している。この2つは元々「1番目=fg、
2番目=bg」の固定位置で、num_order を書かない旧来の宣言順そのままでも
挙動は同じだった（詳しくは `Tech/PluginArgsFreeOrder.md` 参照）。他の
プラグイン（ls/ref/img）と宣言の書きかたを揃えるため、意味は変えずに
num_order/candidate の書式へ揃えた。

rgb()/hsl() のような関数表記を許さないのは、検証を厳しくしたいからではなく
そもそも書けない。インライン記法の正規表現 `PLUGIN_INLINE_RE`
（wikilib/plugins.py）が引数部分を `\\(([^()]*)\\)` としており、
丸括弧そのものを一切含められない仕様のため。引用符で囲んでも、
外側の `&color(...)` 自体にマッチしなくなるため回避できない。

（ブロック側の `PLUGIN_BLOCK_RE` は以前は貪欲マッチで丸括弧の対応を
数えず不具合になっていたが、2026-08-25にwikiSystem本体側で修正され、
今は丸括弧の対応を数えて正しく解決する。インライン側の`[^()]*`は
それとは別の、意図した制約のまま変わっていない。詳しくは
`Tech/PluginBlockParenFix.md`参照）。

expand_inline を宣言しているので、body はインライン記法として展開される
（**太字**やリンクなど）。展開はフレームワーク側がやり直すため、ここでは
エスケープしない。expand_plugin も宣言しているため、body 中の
`&name();`形式のインラインプラグイン記法も展開される（`&color(fg=red)
{&size(115%){text};};`のような、編集画面のツールバーで色→サイズの順に
適用したときに生成される入れ子を正しく表示するため）。expand_block は
宣言していないので、段落・見出しへの展開やブロックプラグイン記法
（`#name(...)`）の展開は対象外（インラインの装飾プラグインという性質上、
インライン記法の入れ子だけで十分なため）。
"""

from wikilib.plugins import PluginArgumentError

COLOR_PATTERN = (
    r"#[0-9a-fA-F]{3,4}"
    r"|#[0-9a-fA-F]{6}"
    r"|#[0-9a-fA-F]{8}"
    r"|[a-zA-Z][a-zA-Z-]{0,30}"
)
COLOR = (COLOR_PATTERN, "re")

PLUGIN_INFO = {
    "help": "&color(fg,bg){文字};",
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "fg", "num_order": 1, "candidate": [COLOR], "default": None, "label": "文字色"},
        {"name": "bg", "num_order": 2, "candidate": [COLOR], "default": None, "label": "背景色"},
    ],
}


def _inline(resolved, body, context):
    fg = resolved["fg"]
    bg = resolved["bg"]
    if not fg and not bg:
        raise PluginArgumentError(
            "文字色・背景色のどちらかを指定してください: &color(fg,bg){文字};"
        )
    if not body:
        raise PluginArgumentError(
            "色を付ける文字を指定してください: &color(fg){文字};"
        )

    styles = []
    if fg:
        styles.append(f"color:{fg}")
    if bg:
        styles.append(f"background-color:{bg}")

    return f'<span style="{"; ".join(styles)}">{body}</span>'
