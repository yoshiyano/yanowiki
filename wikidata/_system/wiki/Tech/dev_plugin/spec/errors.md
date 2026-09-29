# エラーの扱い

#code()

引数の検証、エラーの表示、`_help()` による詳しい説明の仕組みです。

## 引数の検証とエラーの返しかた

`args` で宣言した型（`"bool"`/`"int"`/`"float"`）・`candidate`・必須（`default` 未宣言）は、`_convert` の前に
フレームワークが検証します。宣言では表せない検証（`ls` の `folder` がページとして解決できるか など）は
`_convert` の中で行い、**`wikilib.plugins.PluginArgumentError` を `raise` します。**

```python
from wikilib.plugins import PluginArgumentError

def _convert(resolved, body, context):
    folder = _resolve_folder(context, resolved["folder"])
    if folder is None:
        raise PluginArgumentError(f"フォルダの指定が正しくありません: {resolved['folder']}")
    ...
```

`PluginArgumentError` は、宣言レベルのエラーと同じ見た目で表示され、トレースバックは出ません。
それ以外の例外（想定外の不具合）は次の節のとおり別扱いです。

## 画面での表示のされかた

プラグインの不備は、その箇所だけのエラー表示になり、ほかには影響しません。既定では色付き太字の1行だけです。

```
** ls plugin error : 書きかた: #ls() / #ls(Tech, true, MTIME_REV, TITLE) / …
```

具体的な理由は直す人向けなので、既定では出しません。`plugin.debug` を有効にすると行末に `[詳細]` が付き、
押すと理由と [`_help()`](#_help-で詳しい説明を添える) が開きます。

```yaml
plugin:
  debug: true
```

トレースバックは別の設定で、`config/server.yaml` の `debug: true` か `--debug` 付きの起動で見られます。

```yaml
debug: true
```

### ページの中だけ一時的に有効にする（`#plugin_debug`）

設定を書き換えられない編集者が一時的に `[詳細]` を出したいときは、`plugin_debug` をページに置きます。

```pukiwiki
#plugin_debug(true)     ここより後ろのプラグインのエラーに [詳細] を出す
#plugin_debug(false)    ここより後ろを元の設定（config の plugin.debug）に戻す
```

- このプラグイン自身は何も表示しません
- 効くのは、これより後ろに書かれたプラグインだけです
- 設定の `plugin.debug` が有効なら、`#plugin_debug(false)` でも無効にはできません

### `_help()` で詳しい説明を添える

`_help()` を用意すると、実行できなかったとき（記法に対応していない・引数が正しくない・例外が起きた など）に、
その戻り値を折りたたみで添えます。

```python
def _help():
    return "詳しい書きかたの説明…"
```

`PLUGIN_INFO["help"]` とは役割が違い、同じエラー表示の中に両方とも出ます。

| | いつ出るか | 長さ |
|---|---|---|
| `PLUGIN_INFO["help"]` | 実行できなかったとき、**常に** | 一言（`#hello(name=世界)` のような書きかたの要約） |
| `_help()`（無ければdocstring） | `plugin.debug` が有効なときだけ、折りたたみで**追加** | 詳しい説明（README のようなもの） |

`_help()` が無ければモジュールのdocstringで代用します。`_help()` 自体が例外を投げたときは、説明なしとして扱います。

