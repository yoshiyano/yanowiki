"""writeauth — ページを編集できるユーザを指定する。

    #writeauth(id1,id2,...)

 1. users … 編集を許可するユーザのID（`login`プラグインでログインする
       ときのID）か、`g:グループ名`を`,`区切りで列挙します
       (default: 省略すると、このページの編集権限の記録を削除します)

このプラグインは、**そのページの編集権限（`W`）を`config/privileges.plugin`に
記録するだけ**です。実際に編集を止める処理・止めたときの画面は、記録を読む
wikiSystem本体が行います（`/.admin/privileges`で手で登録する編集の権限と
同じ扱いです）。ページの中には何も表示されません。**`W`は閲覧も含みます**
（編集できる人は、そのページを読めます）。

実在しないユーザ・グループを書くとエラーになります。

**権限を消すには、まず`#writeauth()`（ユーザを書かない空の呼び出し）でページを開いて記録を
削除し、そのあとプラグインの行自体を消します。** 行だけを消した場合も、記録は1時間
以内に自動で消えます（すぐ消すなら`/.updatePageAuth`を開く。誰でも、1時間に10回まで）。

**ページの一番上にだけ置けます。** 途中に書いてあっても、ページを開いたときに
その記述が消えて先頭の行へ移ります（Markdownでタイトル行がある場合は、その直下です）。`#readauth`と両方あれば`readauth`、
`writeauth`の順に並びます。同じプラグインが複数行あれば、**最初に書かれた1行だけ**
が残ります（あとの行は消えます）。
"""

""" 技術資料
`readauth`と同じ作り（`_authcommon.py`。規則・落とし穴・記録の扱いはそちらの
docstring）。違いは種類が`W`であることだけ。

## 本体が`privileges.plugin`を読むようになった（2026-09-23）

本体（`auth.PagePrivilege`）は`privileges.plugin`を読むようになった。優先順位・
緩和しない方向の決まりは`readauth`の技術資料と同じ（[ページごとの権限]
(/Tech/PagePermissions/Evaluate)の「`config/privileges.plugin`との優先順位」）。

## 誰でも自分のページの権限を決められる

`#writeauth`は、そのページを**編集できる人なら誰でも書ける**（プラグインの
呼び出しは、本文を書ける人の書きものにすぎない）。「権限を与えられるのは
ページ編集者と助手」という本体の決めごと（`Tech/PagePermissions`）のとおりで、
編集の権限を締めておくことが先（同「編集できる人は、自分に閲覧権限を書ける」）。
"""
import importlib.util
import os

PLUGIN_INFO = {
    "help": "#writeauth(users)",
    "args": [
        {"name": "users", "rest_params": True},
    ],
}


def _load_common():
    """兄弟の`_authcommon.py`を読み込む（呼び出しごと。理由は`_authcommon.py`の docstring）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_authcommon.py")
    spec = importlib.util.spec_from_file_location("wikiplugin__authcommon", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _convert(resolved, body, context):
    return _load_common().run("writeauth", "W", resolved, context)
