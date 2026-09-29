# 引数の宣言

`PLUGIN_INFO` の `args` で引数を宣言すると、本体が解釈と検証を行います。各項目の詳しい使いかたは [引数の宣言の項目](/Tech/dev_plugin/spec/args_options) にあります。

### 引数の宣言（`args`）

受け取りたい引数を [`PLUGIN_INFO`](/Tech/dev_plugin/plugin_info) の `"args"` に並び順どおりに宣言すると、
本体が解釈と検証を行います（`_convert` の中で自分で解釈すると、[落とし穴](#位置引数は名前で埋まった枠を飛ばす)があります）。

```python
PLUGIN_INFO = {
    "args": [
        {"name": "folder"},                                          # defaultが無い＝必須
        {"name": "recursive", "type": "bool", "default": False, "label": "再帰"},
        {"name": "num", "type": "int", "default": 10, "min": 1, "label": "表示件数"},
    ],
}
```

| 項目 | 意味 |
|---|---|
| `name` | 引数名。位置引数の何番目に対応するかは、既定では宣言の並び順で決まる（[`num_order`](/Tech/dev_plugin/spec/args_options#引数を自由な順番で書けるようにするnum_order)を使うと切り離せる） |
| `type` | `"bool"` / `"int"` / `"float"` / 省略（文字列のまま） |
| `min` / `max` | `"int"`/`"float"` のときだけ使える範囲チェック |
| `candidate` | 許容する値の一覧（既定は大文字小文字を区別しない完全一致。正規表現・大文字小文字を区別する一致も混ぜられる。[詳しくは後述](/Tech/dev_plugin/spec/args_options#candidate-の検証)） |
| `default` | 省略されたときの値。この項目を宣言していなければ必須になる |
| `label` | エラー文言に使う日本語名（省略時は `name` をそのまま使う） |
| `num_order` | 位置引数の何番目に対応するかを、宣言順から切り離して指定する（[詳しくは後述](/Tech/dev_plugin/spec/args_options#引数を自由な順番で書けるようにするnum_order)） |
| `flag` | 「項目名と同じ単語が書かれていれば`True`」という真偽フラグの糖衣構文（[詳しくは後述](/Tech/dev_plugin/spec/args_options#flag-単語を書くだけで有効になる真偽フラグの糖衣構文)） |

**`default` を宣言していない項目は必須です**（省略や空文字列はエラー）。必須でない項目には `"default": None` などを
明記します。エラーになるかは、値ではなくこのキーがあるかどうかで決まります。

```python
{"name": "target", "label": "対象"}
    → defaultが無いので必須。省略すると「対象を指定してください。」でエラーになる

{"name": "target", "default": "fallback", "label": "対象"}
    → 省略すると "fallback" になる（エラーにならない）

{"name": "note", "default": None, "label": "備考"}
    → 省略すると None になる（エラーにならない。値は気にしない、というだけの宣言）

{"name": "note", "default": "", "label": "備考"}
    → 省略すると "" になる（エラーにならない。None か "" かは意味の違いだけ）
```

位置引数がどの枠に入るかは、既定では宣言の並び順で決まります（`num_order` で変えられます）。

```python
"args": [{"name": "folder"}, {"name": "recursive", "type": "bool"}, {"name": "sort", "default": "FNAME"}]
```

```pukiwiki
#ls(Tech, true, MTIME)
    → folder="Tech", recursive=True, sort="MTIME"（宣言順どおり）
```

### 位置引数は、名前で埋まった枠を飛ばす

位置引数は、名前で埋まった枠を飛ばして次の枠に入ります。`#ls(folder=Tech, true)` の `"true"` は2つ目の枠
（`recursive`）に入ります（生の位置番号で読むと取りこぼします）。カンマの間を空けると、その位置を飛ばせます。

```pukiwiki
#ls(, , TITLE)
    → folder と recursive は既定のまま、sort だけ TITLE を指定
```

### 「ブロック専用にしたい引数」は`_inline`側で参照しないだけでよい

`_inline` の中でその名前を参照しなければ済みます（本家と同じく、インラインで書かれても黙って使われません）。

### 具体例（`ref`）

```python
"args": [
    {"name": "src", "num_order": 1, "link": True},
    {"name": "size", "default": None, "candidate": [(SIZE_PATTERN, "re")], "label": "大きさ"},
    {"name": "align", "default": "LEFT", "candidate": ["LEFT", "CENTER", "RIGHT"], "label": "寄せ"},
    {"name": "wrap", "flag": True, "default": False, "label": "枠"},
    {"name": "nolink", "flag": True, "default": False, "label": "リンクなし"},
    # …（around・noicon・noimg・zoom も同じ flag の形）
    {"name": "title", "num_order": -1, "default": None},
]
```

```pukiwiki
#ref(file.jpg, wrap, nolink, right)   → 本家と同じ、順不同で好きなだけ書ける
```

`resolved` には、名前をキーに束ねた値が型変換まで済んで入ります（変換できなければ `_convert` の前にエラー）。

```python
def _convert(resolved, body, context):
    if resolved["wrap"]:
        ...
```

プラグイン固有の検証（`ls` の `folder` がページとして解決できるか など）は、`_convert` の中で行います
（[エラーの扱い](/Tech/dev_plugin/spec/errors#引数の検証とエラーの返しかた)）。
