# プラグインのwhole_page改名・dynamic_output追加（要望）

wikiPlugin から wikiSystem 本体（`_sys/wikilib/paths.py`・`plugins.py`）への実装依頼です。
**2026-08-24に対応済みです**（[プラグインの作りかた](/Tech/dev_plugin)）。
`plugin/contents.py` も `need_outer_info` を宣言する形に書き換えてあります。

## 背景：2つの別の軸

`PLUGIN_INFO["whole_page"]` は、[セクション編集](/Tech/SectionEditing)の部分プレビューで
そのプラグインを実行しない（断り書きを出す）ことだけを制御していました
（`call_plugin` の `info.get("whole_page") and context.partial`）。宣言していたのは `contents` だけです。

一方、プラグインの出力をHTMLとしてキャッシュする機能を検討しており、そこでは
**同じ引数・中身でも出力が時間とともに変わる**プラグイン（`ls`・`recent` など）を区別する必要があります。

この2つは別の軸です。

| | 入力が引数・中身だけで決まらない | 出力が時間で変わる |
|---|---|---|
| `contents` | はい（ページ全体の見出しを見る） | いいえ |
| `ls`・`recent` | いいえ | はい（DBの更新状況で変わる） |

1つのフラグにまとめると片方だけに当たるプラグインを表せないので、2つに分けました。

## `need_outer_info`（`whole_page` の改名。動きは同じ）

```python
PLUGIN_INFO = {"need_outer_info": True}
```

既定値（`False`）も、参照する場所（`call_plugin` の `context.partial` の判定）も同じで、
名前だけを変えました。ページ全体に限らず、**引数・中身だけでは決まらない外部の情報**
（ページ全体の見出し・他のページ・DBの状態・現在時刻など）が要るなら宣言します。

## `dynamic_output`（新設。宣言を受け付けるだけ）

```python
PLUGIN_INFO = {"dynamic_output": True}
```

同じ引数・中身でも出力が時間とともに変わりうることを表します。キャッシュ機能はまだ無いので、
参照する処理もありません。`PLUGIN_DEFAULT_INFO` に `False` で登録し、宣言できる項目として
[プラグインの作りかた](/Tech/dev_plugin)の表に載せています。

## 切り替えの順番

`contents.py` の書き換えは、本体の改名が入ってから行いました。先に書き換えると、
本体が読む名前が無くなり、部分プレビューでの判定が効かなくなるためです。
