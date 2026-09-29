# プラグイン引数の自由順序化（要望）

wikiPlugin から wikiSystem 本体（`_sys/wikilib/plugins.py`）への実装依頼です。
**2026-08-23に実装済みです**（`num_order`・`candidate` のタプル拡張・`FREE_TEXT`・
`flag`・`block_only` の廃止）。
使いかたは [プラグイン仕様](/Tech/dev_plugin/spec/args_options#引数を自由な順番で書けるようにするnum_order) にあります。

## 背景

`PLUGIN_INFO["args"]` は宣言順がそのまま位置引数の順番だったため、使いたいオプションだけを
書くには `#ref(file.jpg, , , true)` のように空の位置を飛ばす必要があり、文章を書く人には
分かりにくいものでした。本家PukiWikiの `ref`・`img`・`comment` などはオプションを好きな順番で
並べられるので、その使い勝手を宣言的な `args` の枠組みで再現します。

## 仕様

### `num_order`

| 値 | 意味 |
|---|---|
| 正の整数 | 位置引数の何番目に固定するか（1始まり）。1からの連番でなければ読み込み時のエラー。宣言順が昇順でなければコンソールに警告 |
| 負の整数 | どのオプションにも当てはまらなかった残りを全部拾い、`","` で連結する（本家 `ref` のタイトルと同じ） |
| 書かない | 自由な位置・順序。どのトークンに当たるかは `candidate` で決まる |

自由順序の項目は現れる保証が無いので、`default` を持たないとエラーです。必須の値は位置を固定します。

### 位置引数の解決順序

1. 正の `num_order` を1番から順に埋める。トークンが空なら `default`、値があって合わなければ検証エラー
2. 残りのトークンを、自由順序の項目に**宣言順で**試す。複数に当てはまるなら先に宣言したほうに決まり、
   一度決まったトークンは他へ回らない（`color` の `fg`・`bg` のように候補が重なると、後のほうは
   `bg=…` と名前で書くしかない）
3. 残ったトークンは負の `num_order` の項目へ。その項目が無ければエラー（原因が分かるものはその旨、
   分からなければ「引数の解釈に失敗しました」）

### `candidate` の拡張

文字列（大文字小文字を区別しない完全一致）に加えて、2要素のタプルを混ぜられます。
配列の先頭から見て最初に一致したものを採ります。

```python
{"name": "size", "candidate": [(r"^\d+x\d+$", "re"), ...]}        # 正規表現（re.fullmatch）
{"name": "code", "candidate": [("AB", "case"), ("ab", "case")]}   # 大文字小文字を区別する完全一致
```

何にでも一致する `FREE_TEXT = ("^.*$", "re")` を `wikilib.plugins` に置きます。自由順序で使うと
意図しない値まで拾うので、`num_order` で位置を固定して使います。

### `"flag": True`

`{"name": "wrap", "flag": True, "default": False}` は
`{"name": "wrap", "candidate": ["wrap"], "type": "bool", "default": False}` の省略形です。
名前と同じ単語が書かれていれば `True` になります。`wrap=false` のような打ち消しはありません。

### `block_only` の廃止

自由順序になれば、インラインとブロックで位置を詰め替える必要が無くなります。ブロック専用の
オプションは、`_inline()` がそのキーを見ないだけで済みます（本家も、インラインで書かれた
ブロック専用のオプションは黙って無視します）。

## 例

`color` は `fg`・`bg` が同じ色の正規表現を共有するので、位置を固定します（元の `color.py` と
動きは同じ）。

```python
{"name": "fg", "num_order": 1, "candidate": [COLOR_PATTERN_TUPLE], "default": None},
{"name": "bg", "num_order": 2, "candidate": [COLOR_PATTERN_TUPLE], "default": None},
```

`ls` は `folder` を1番目に固定し、`recursive`・`ajaxview` を単語のフラグ、`sort`・`format` を
自由順序にします。書きかたは `#ls(Tech, recursive, MTIME_REV)` です。

依頼時の例にあった `#ls(ajaxview, Tech)` は誤りでした。`folder` は1番目に固定なので
`ajaxview` を受け取り、`Tech` はどの候補にも当たらずエラーになります（仕様どおりの動き）。
wikiPlugin 側で例を `#ls(Tech, ajaxview, TITLE)` に直しました。フラグを先に書きたいときは
`#ls(folder=Tech, ajaxview)` と名前で書きます。

`ref` は `src` を1番目に固定し、`wrap`・`nolink` などを `flag`、`title` を負の `num_order` に
しました。`#ref(file.jpg, wrap, nolink, right)` のように順不同で書けます。
