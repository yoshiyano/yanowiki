# 引数の宣言の項目

`args` の各項目に付けられる、順番・検証・参照・可変長・フラグの指定です。宣言の基本は [引数の宣言](/Tech/dev_plugin/spec/args) にあります。

### 引数を自由な順番で書けるようにする（`num_order`）

オプションの多いプラグインで、`#ref(file.jpg, , , true)` のように空の位置を飛ばさず、本家PukiWikiの
`ref`/`img` のように好きな順で書けるようにします（[経緯](/Tech/PluginArgsFreeOrder)）。

**`args` の中で1つでも `num_order` を書くと、その `args` 全体がこの解決順序になります**（宣言順の位置引数と
混ぜることはできません）。1つも書かなければ、上の動作のままです。

```python
"args": [
    {"name": "fg", "num_order": 1, "candidate": [COLOR], "default": None},
    {"name": "bg", "num_order": 2, "candidate": [COLOR], "default": None},
    {"name": "wrap", "flag": True, "default": False},
    {"name": "title", "num_order": -1, "default": None},
]
```

- **正の整数**: 位置引数の何番目に固定するか（1始まり）。1からの連番でなければ読み込みが失敗します
  （`1, 3` はエラー）。宣言順が昇順でなければ、サーバーコンソールに警告が出ます。値が空なら `default`、
  値があって `candidate` に合わなければ検証エラーです。
- **負の整数**（`-1` だけ、`args` に1つまで。2つ以上は読み込みが失敗）: どの項目にも当てはまらなかった位置引数を
  全部拾って `","` で連結します。連結結果には `candidate`/`type` の検証がかかりません（複数の値をまとめた文字列の
  ため）。`名前=値` で書いた場合は連結せず、検証もかかります。
  [`rest_params`](#rest_params-残りの位置引数を丸ごと受け取る可変長引数) と違い、ほかの項目との併用が前提です。
- **無し**: 自由な位置・順序。残った位置引数を宣言順に試し、`candidate` に一致した最初の項目が受け取ります。
  一度決まったトークンは他へ回りません。`candidate` の無い項目は何にでも一致するので、ほかの自由順序の項目より
  後ろに書きます。

**`num_order` を使う `args` では、`num_order` を書かない項目に `default` が必須です**（書かれているかどうかで
存在を判定するので、必須にできない。守られていなければ読み込みが失敗します）。

どの項目にも当てはまらない位置引数が残り、かつ負の`num_order`の項目も
無い場合は「引数の解釈に失敗しました。」でエラーになります。

### `candidate` の検証

`candidate`（許す値の一覧）は、型変換より先に生の文字列を照合します。要素には、文字列（大文字小文字を区別しない
完全一致）と、`(パターン, 種別)` のタプル（`"re"`＝`re.fullmatch`、`"case"`＝区別する完全一致）を混ぜられます。

```python
{"name": "sort", "candidate": ["FNAME", "MTIME", "TITLE"], "default": "FNAME"}
    → 一覧に無い値を書くとエラーになる

{"name": "align", "candidate": ["LEFT", "CENTER", "RIGHT"]}          # 文字列は既定どおり大文字小文字を区別しない完全一致
{"name": "code", "candidate": [(r"[A-Za-z]{2}-\d{3}", "re")]}        # 正規表現（re.fullmatchで全体一致）
{"name": "id", "candidate": [("AB", "case"), ("ab", "case")]}        # 大文字小文字を区別する完全一致
```

一覧の先頭から見て最初に一致したものを採ります。文字列の要素に一致したときは、値を候補側の表記に揃えます
（`"fname"` → `"FNAME"`）。タプルに一致したときは、書いたままの値です。

```python
{"name": "sort", "candidate": ["FNAME", "MTIME"], "default": "FNAME"}
    → "fname" と書いても resolved["sort"] は "FNAME" になる（区別しない）
```

自由な文字列は `wikilib.plugins` の `FREE_TEXT`（`("^.*$", "re")`）で受け、`num_order` で位置を固定します
（自由順序にすると、意図しない値まで拾います）。

```python
{"name": "folder", "num_order": 1, "candidate": [FREE_TEXT], "default": None}
```

**宣言に無い引数はエラーです**（位置引数が多すぎる場合も、知らない名前の場合も）。黙って無視すると、効いている
つもりのまま気づけないためです。

```python
"args": [{"name": "folder"}, {"name": "recursive", "type": "bool"}]
    → #ls(Tech, true, extra) は「引数が多すぎます（2個までです）。」でエラー
    → #ls(folder=Tech, unknown=1) は「知らない引数です: unknown」でエラー
```

宣言だけでは判断できない検証は、`_convert` の中で行います（[エラーの扱い](/Tech/dev_plugin/spec/errors#引数の検証とエラーの返しかた)）。

### `link`: 引数の値をページ/添付への参照として扱う

```python
{"name": "folder", "default": None, "link": True}
```

`link: True` を付けた引数の値は、本文中のリンクと同じくリンク元のデータベースに記録され、参照先の
「ここから参照されています」にも出ます。外部URLやInterWikiかどうかは自動で判定します。

```python
#ls(folder=Tech/ChangeLog)   # folder に link:True があれば、リンク元として記録される
#img(src=https://example.com/a.png)  # 外部URLは自動的に対象外
```

ブロック・インラインのどちらでも働きます。プラグインを実行せず宣言だけで値を取り出すので、副作用のある
プラグインでも安全です。リネーム時には、この値も新しい名前に直ります（[リネームの仕組み](/Tech/RenamePage)）。

### `rest_params`: 残りの位置引数を丸ごと受け取る（可変長引数）

```python
"args": [{"name": "a"}, {"name": "rest", "rest_params": True}]
```

`rest_params: True` の引数は、残っている位置引数をすべて `","` で結合した文字列を受け取ります（無ければ `""`）。

```python
#name(1, x, y, z)   → a="1", rest="x,y,z"
#name(1)            → a="1", rest=""
```

型変換・`candidate`・必須の判定は行いません。`rest=値` とは書けません（「知らない引数です」になる）。
`rest_params` より後ろの宣言は無視され、読み込み時にサーバーコンソールへ警告が出ます。

```python
"args": [
    {"name": "a"},
    {"name": "rest", "rest_params": True},
    {"name": "b", "default": None},  # ← 無視される。読み込み時に警告が出る
]
```

[`num_order`](#引数を自由な順番で書けるようにするnum_order) とは別の仕組みです。`num_order` を使う `args` では、
負の `num_order` を使います（同じ項目に両方を書いた場合の扱いは決めていません）。

### `flag`: 「単語を書くだけで有効になる」真偽フラグの糖衣構文

```python
{"name": "wrap", "flag": True, "default": False}
```

は、次の省略記法です。

```python
{"name": "wrap", "candidate": ["wrap"], "type": "bool", "default": False}
```

名前と同じ単語が書かれていれば `True` です。`wrap=false` のような打ち消しは書けません（エラーになる）。
`num_order` の有無に関わらず使えます（読み込み時に `_expand_flag_sugar` が展開します）。
