"""readauth — ページを閲覧できるユーザを指定する。

    #readauth(id1,id2,...)

 1. users … 閲覧を許可するユーザのID（`login`プラグインでログインする
       ときのID）か、`g:グループ名`を`,`区切りで列挙します
       (default: 省略すると、このページの閲覧権限の記録を削除します)

このプラグインは、**そのページの閲覧権限を`config/privileges.plugin`に記録する
だけ**です。実際に閲覧を止める処理・止めたときの画面は、記録を読む
wikiSystem本体が行います（`/.admin/privileges`で手で登録する閲覧の権限と
同じ扱いです）。ページの中には何も表示されません。

実在しないユーザ・グループを書くとエラーになります。

**権限を消すには、まず`#readauth()`（ユーザを書かない空の呼び出し）でページを開いて記録を
削除し、そのあとプラグインの行自体を消します。** 行だけを消した場合も、記録は1時間
以内に自動で消えます（すぐ消すなら`/.updatePageAuth`を開く。誰でも、1時間に10回まで）。

**ページの一番上にだけ置けます。** 途中に書いてあっても、ページを開いたときに
その記述が消えて先頭の行へ移ります（Markdownでタイトル行がある場合は、その直下です）。`#writeauth`と両方あれば`readauth`、
`writeauth`の順に並びます。同じプラグインが複数行あれば、**最初に書かれた1行だけ**
が残ります（あとの行は消えます）。
"""

""" 技術資料
`config/privileges.plugin`への記録と先頭行への寄せは、`writeauth`と共有する
`_authcommon.py`が行う（規則・落とし穴・記録の扱いはそちらの docstring）。
このファイルは名前と種類（`R`）を渡すだけ。

## 旧名 viewaccess（2026-09-21に改名）と、役目の変更

`viewaccess`から`readauth`へ改めた（書き込みの権限を扱う`writeauth`と対にする
ため）。**旧名はもう動かない**（別名は残していない）。改名前の
`#viewaccess(...)`を書いたページは、プラグインが見つからないエラーになる。

改名の直後は`context.block_view`（のち`context.deny_view`）で自分で表示を止めて
いたが、**同じ日のうちに、記録だけを担当する形に改めた**（Wiki設計者の指示。
「表示停止などの処理をする必要はありませんでした。`privileges.plugin`の更新のみを
担当してください。`privileges`の扱いの延長で、本体が参照して処理します」）。
このため次のことが変わった。

- **表示は止めない。** 権限が無いときの画面も本体が出す。以前あった案内文
  （`#readauth(...){案内}`の`{}`）は使われなくなった。**書いても黙って無視する**
  （エラーにしないのは、書かれていた既存のページを壊さないため）
- **`block_view`は、他のプラグインを含めて使える窓口として本体に残っている**
  （`viewable_period`が使っている）。ここでは使わない

## 本体が`privileges.plugin`を読むようになった（2026-09-23）

本体（`auth.PagePrivilege`）は`privileges.plugin`を読むようになった。**手で書く
`config/privileges`より優先されるが、緩和する方向には働かない**（Wiki設計者の
指示）——`#readauth`で絞ったページは、`config/privileges`がどれだけ緩くても
絞られたままになる。逆に、`config/privileges`のほうが厳しければ、`#readauth`
で緩めることはできない。詳しくは[ページごとの権限](/Tech/PagePermissions/Evaluate)の
「`config/privileges.plugin`との優先順位」。
"""
import importlib.util
import os

PLUGIN_INFO = {
    "help": "#readauth(users)",
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
    return _load_common().run("readauth", "R", resolved, context)
