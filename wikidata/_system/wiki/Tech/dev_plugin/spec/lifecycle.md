# 実行時の呼ばれかた

`_action`・`_setup` が呼ばれるタイミングと注意点です。

## `_action` でコマンドやAPIを提供する

`/.plugin/<プラグイン名>` にアクセスすると `_action(context)` が呼ばれます。フォームの送信先やAPIに使います。

```python
def _action(context):
    return "<p>呼ばれました</p>"
```

別のWikiを明示している場合は `/=sandbox/.plugin/<名前>` のようにWiki名が付きます。
`_action` を持たないプラグインや存在しない名前は `no page`（404）です。

クエリは `from bottle import request` で読みます（`ls` の読み込みAPIの例）。

```python
def _action(context):
    from bottle import request

    pagepath = (request.query.getunicode("page", "") or "").strip("/")
    ...
```

## _setup の呼ばれかた

`_setup(context)` は**HTTPリクエストごとに1回**呼ばれます。プラグインのファイルもリクエストごとに読み直すので、
編集は再起動しなくても反映されます。その代わり、モジュールの状態はリクエストをまたいで残らないので、
共有したいデータは `_setup` の中で読み直す前提で書きます。

**1つのリクエストの中では、読み込んだモジュールを使い回します**（2026-09-27）。`#pagediv`・`#include` などで別のページを
差し込むと、そのページの描画も同じモジュールで行われます。描画ごとの状態はモジュールの変数ではなく `context` に持たせてください
（モジュールの変数に置くと、差し込んだページと差し込み元とで混ざります）。

戻り値は見ません。`context` に属性を足すなどして、`_convert`/`_inline`/`_action` へ情報を渡します。

`_setup` が例外を投げると、そのリクエストの間そのプラグインは使えず、どの関数を呼んでも「プラグインの読み込みで
エラーが発生しました」と出ます。ほかのプラグインには波及しません。

### `_sys/wikilib/` を直したときは再起動が要ります

読み直されるのはプラグインのファイルだけで、`_sys/wikilib/` は起動時のものが動き続けます。`wikilib` に足した
関数をプラグインから `import` しても、再起動しなければ読み込みに失敗して次のように出ます。

```
#ls  プラグインの読み込みでエラーが発生しました
```

`--debug` で起動していれば `ImportError: cannot import name '…'` と出ます。[再起動](/Tech/Restart)で直ります。

