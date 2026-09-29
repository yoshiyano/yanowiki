# color — 文字色・背景色を指定する

| 使える記法 | |
|---|---|
| ブロック `#color()` | × |
| インライン `&color();` | ○ |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

#code()

文中の一部に文字色・背景色を付けます。書きかたは PukiWiki の `&color()` と同じで、出力は `<span style="color:...">` です。

### 書きかた

```pukiwiki
&color(fg){文字};                  文字色だけ
&color(fg, bg){文字};              文字色と背景色
&color(, bg){文字};                背景色だけ（fgを飛ばす）
&color(fg=red, bg=yellow){文字};   名前付きでも書ける
```

| 引数 | 値 | 既定 | 意味 |
|---|---|---|---|
| `fg` | 色の指定 | なし | 文字色 |
| `bg` | 色の指定 | なし | 背景色 |

- `fg`・`bg` の少なくとも一方が要ります（[引数の宣言（args）](/Tech/dev_plugin/spec/args#引数の宣言args)参照）
- 色は `red` のような色名か、`#f00`／`#ff0000`／`#ff0000cc`（アルファつき）のような16進です。`rgb()` のような丸括弧の関数表記は書けません（引数に丸括弧を書けないため）
- 中身にはインライン記法（太字・リンクなど）が使えます。ブロック要素や、ほかのプラグインの入れ子は展開されません

### 表示例

```pukiwiki
&color(red){赤い文字}; / &color(white, crimson){白地に紅色}; / &color(, lightyellow){背景色だけ}; / &color(#0066cc){16進}; / &color(fg=red){**重要**な[リンク](/)};
```

&color(red){赤い文字}; / &color(white, crimson){白地に紅色}; / &color(, lightyellow){背景色だけ}; / &color(#0066cc){16進}; / &color(fg=red){**重要**な[リンク](/)};

`&color(white, crimson){…};` の出力は `<span style="color:white; background-color:crimson">…</span>` です。

### エラーになる書きかた

| 書きかた | 理由 |
|---|---|
| `&color(){文字};` | `fg`・`bg` を両方省略した |
| `&color(notacolor!){文字};` | 色の指定が16進・色名のどちらの形にも合わない |
| `&color(red){};` | 中身が無い |

詳しくは [共通の書きかた](/Syntax/Common#うまく動かないとき) を参照してください。
