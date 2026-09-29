"""size — 文字の大きさ（フォントサイズ）を指定するインラインプラグイン。

    &size(px){文字};      ピクセル数で指定
    &size(割合%){文字};   元の大きさに対する割合（相対指定）

PukiWikiの `&size()` に合わせた書きかたです。CSSの `font-size` で
文字の大きさを変えます。

 1. **px または 割合%** … 文字の大きさ（省略不可）
       pxは 8〜60 の範囲に丸められます（8未満なら8、60を超えるなら60）。
       割合（%）は 10〜500 の範囲に丸められます

中身にはインライン記法（**太字**やリンクなど）が使えます。
"""

""" 技術資料
px の範囲（8〜60）・範囲外を丸める挙動は、本家PukiWiki
（PLUGIN_SIZE_MIN/PLUGIN_SIZE_MAX、`max(MIN, min(MAX, size))`）に完全互換。
割合（%）は本家に無い拡張（編集画面のツールバーで「元の大きさに対する
増減」を選べるようにするための追加。詳しくは`Tech/dev_plugin` ではなく
編集画面側のツールバー機能を参照）。CSSの `font-size:110%` がそのまま
「周囲の文字に対する相対値」になるので、基準pxへ換算する必要がない。

`PLUGIN_INFO["args"]` の `type`/`min`/`max` は使わない（pxか%かで別々の
範囲・単位になり、型変換より先に% の有無で分岐する必要があるため）。
`candidate` の正規表現で「数字＋任意の%」という形だけを検証し、
実際の範囲チェックと丸めは `_clamp()` で自前に行う。

style属性に display:inline-block; line-height:130%; text-indent:0 を
添えているのは本家と同じ理由。font-sizeを地の文より大きくすると、行の
高さがずれたり、その行の他の文字と重なって見えたりする。inline-blockに
した上で行の高さと字下げを打ち消しておくと、周囲の行を崩さずに大きさだけ
変えられる。

expand_inline を宣言しているので、body はインライン記法として展開される。
展開はフレームワーク側がやり直すため、ここではエスケープしない
（colorプラグインと同じ理由）。expand_plugin も宣言しているため、body
中の`&name();`形式のインラインプラグイン記法も展開される（colorと
size を続けて適用したときに生成される入れ子を正しく表示するため。
詳しくはcolorプラグインの技術資料参照）。
"""

from wikilib.plugins import PluginArgumentError

PX_MIN = 8
PX_MAX = 60
PERCENT_MIN = 10
PERCENT_MAX = 500

SIZE_PATTERN = (r"\d+%?", "re")

PLUGIN_INFO = {
    "help": "&size(px または 割合%){文字};",
    "expand_inline": True,
    "expand_plugin": True,
    "args": [
        {"name": "size", "candidate": [SIZE_PATTERN], "label": "文字の大きさ"},
    ],
}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _inline(resolved, body, context):
    if not body:
        raise PluginArgumentError(
            "大きさを変える文字を指定してください: &size(px){文字};"
        )

    raw = resolved["size"]
    if raw.endswith("%"):
        value = f"{_clamp(int(raw[:-1]), PERCENT_MIN, PERCENT_MAX)}%"
    else:
        value = f"{_clamp(int(raw), PX_MIN, PX_MAX)}px"

    style = f"font-size:{value};display:inline-block;line-height:130%;text-indent:0"
    return f'<span style="{style}">{body}</span>'
