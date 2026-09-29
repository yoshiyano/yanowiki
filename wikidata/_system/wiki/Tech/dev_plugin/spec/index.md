# プラグイン仕様

#code()

呼び出しの記法と、引数の宣言（`args`）です。`args` 以外の項目は [PLUGIN_INFO](/Tech/dev_plugin/plugin_info) にあります。

ブロックは3つの形です。`#` の直後に空白を入れないので、見出し（`# 見出し`）とは衝突しません。

```pukiwiki
#name(args)              引数だけ
#name(args){中身}         1行で書ける中身つき
#name(args){{            複数行の中身
...
}}
```

複数行の中身に `{{{` のような波括弧が含まれる場合は、それより多い数で囲みます（`{{{{` … `}}}}`）。

3つのどれにも当てはまらない書きかた（`{{中身}}` を1行で書いた、`{{` を閉じ忘れた など）も、文字列にせず
エラーにします（何が悪いのか気づけるように）。ブロックプラグインはリスト項目や引用の中でも動きます。

インラインは2つです。

```pukiwiki
&name(args);
&name(args){中身};
```

引数はカンマ区切りで、`key=value` は名前付き引数、それ以外は位置引数です。カンマや `=` を含む値は
`"` か `'` で囲みます（中にもう一方の引用符を混ぜられます）。引用符のエスケープはありません。

```pukiwiki
#note(warn, label="カンマ, を含む値")
    → 位置引数 ["warn"]、名前付き引数 {"label": "カンマ, を含む値"}
```

### 括弧を省いた `&name;` について

引数が要らないプラグインは、括弧を省いた `&name;` でも呼べます。

ただし、**プラグイン名がHTML5の文字実体参照名（`copy`・`amp`・`nbsp`・`hellip` など）と同じだと使えません。**
`wikilib.pukiwiki.inline_match` は `&name;` が `html.entities.html5` に載っていれば先に実体参照として扱うので
（`&copy;` を `©` にするため）、同名のプラグインは括弧なしでは呼べません。

```pukiwiki
&copy;      → © として解決される（同名のプラグインがあっても呼ばれない）
&copy();    → プラグイン copy が呼ばれる（括弧を付ければ回避できる）
```

プラグインの名前は、HTML5の実体参照名と重ならないものにします（重なるなら、必ず `&name();` と書くよう案内します）。
一覧は次で出せます（`copy` が載っているかも調べる例）。

```bash
python3 -c "from html.entities import html5; a=sorted({k[:-1] for k in html5 if k.endswith(';')});print(a, 'copy' in a)"
```

### 引数の宣言

引数の宣言（`args`）の決まりは [引数の宣言](/Tech/dev_plugin/spec/args)、各項目
（`num_order`・`candidate`・`link`・`rest_params`・`flag`）の使いかたは
[引数の宣言の項目](/Tech/dev_plugin/spec/args_options) にあります。
