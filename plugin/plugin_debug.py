"""plugin_debug — このページの中だけ、`plugin.debug`相当の表示を一時的に
切り替えるブロックプラグイン。

    #plugin_debug(true)     以降のプラグインのエラーに [詳細] を出す
    #plugin_debug(false)    以降を元の設定（config の plugin.debug）に戻す

`config/default.yaml` の `plugin.debug` は、プラグインが動かなかったとき
[詳細]（理由と`_help()`）を出すかどうかの設定ですが、記事を書くだけの人が
気軽に config を書き換える権限を持てるとは限りません。動作検証のために
一時的に有効にしたいだけなら、このプラグインをページの中に置いてください。

 1. bool … true/false（true/yes/on/1、false/no/off/0のいずれも使えます。
       省略不可）

**このプラグイン自身は、ページに何も表示しません。** 効果があるのは
**このプラグインより後ろに書かれた**プラグインのエラー表示だけです
（ページは上から順番に描画されるため）。`config`側の`plugin.debug`が
既に有効な場合、`#plugin_debug(false)`を書いても無効にはできません
（configの設定が常に優先されます）。
"""

""" 技術資料
`context.plugin_debug_override`（`wikilib.plugins.PluginContext`が持つ、
既定`False`のフラグ）を書き換えるだけの副作用専用プラグイン。実際に
[詳細]を出すかどうかの判定（`wikilib.plugins.plugin_debug_enabled(context.config)
or context.plugin_debug_override`）は、呼び出し側（`wikilib.plugins`の
render_plugin/handle_plugin_action）がORで合わせて決める。ここでは
config側の値をこちらから読み書きしない——「configが有効なものを無効化は
できない」という一方向の関係を、この一箇所（呼び出し側のOR）だけで
保証するため。

`context`は1回のページ描画で使い回される同じインスタンスなので、書いた
効果はここで戻り値を返したあとも、同じ描画の中で後続のプラグインへ
そのまま残る（Markdownのブロックはトークン列を上から順にレンダーする
ため、途中で切り替えれば以降だけに効く）。
"""

PLUGIN_INFO = {
    "help": "#plugin_debug(bool)",
    "args": [
        {"name": "value", "type": "bool", "label": "plugin.debugを有効にするか"},
    ],
}


def _convert(resolved, body, context):
    context.plugin_debug_override = resolved["value"]
    return ""
