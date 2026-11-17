# htmlref — 管理者が承認した添付の HTML を、スクリプトを動かして開く

| 使える書きかた | |
|---|---|
| ブロック `#htmlref()` | ○ |
| インライン `&htmlref();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

#code()

添付ファイルの HTML へのリンクを出します。

添付の HTML は、ふだん（[ref](/Syntax/Plugin/ref) のリンクや `/.attach/…`）は**スクリプトが動かない形**で開きます。
`#htmlref` で参照し、**管理者が承認した HTML だけ**、スクリプトが動く形で開きます。

### 書きかた

```pukiwiki
#htmlref(src)                     書いて保存する（承認待ちの印が書き足されます）
#htmlref(src, title=説明書)        表示する文字を変える
```

| 引数 | 値 | 既定 | 意味 |
|---|---|---|---|
| **`src`** | 添付ファイル名 | なし（**省略不可。常に1番目**） | 参照する HTML（拡張子が `html`・`htm`・`HTML`・`HTM` のもの） |
| `allow` | `req`＋2文字、`as_`＋10文字 | 無し | 承認待ちの印か、承認のキー。**自分では書きません**（下記） |
| `title` | 任意の文字 | ファイル名 | 表示する文字。**`title=…` と名前を付けて書きます** |

- `src` の指しかたは、ほかのリンクと同じ規則です（[共通の書きかた](/Syntax/Common) 参照）。別のページの添付も指せます
- 中身（`{…}`）は使いません

### 承認の流れ

1. 書き手が `#htmlref(demo.html)` と書いて保存します
2. そのページを開くと、`#htmlref(demo.html, reqAB)` のような**承認待ちの印**が本文に書き足されます（`AB` はページの中で重ならない2文字）。リンクには「スクリプト承認待ち」と添えられ、開いてもスクリプトは動きません
3. 管理者がそのページを開くと、承認待ちの `#htmlref` に［承認］ボタンが出ます。押すと印が**承認のキー**に書き換わります（`#htmlref(demo.html, as_4GPjsKgOeJ)`）
4. 以後、そのリンクには「スクリプト許可」と添えられ、開くとスクリプトが動きます

- ［承認］ボタンは、そのページを直接開いたときだけ出ます。メニューや [include](/Syntax/Plugin/include) で差し込んだページの中では出ないので、差し込み元のページを開いて承認してください
- 同じページに同じ印が2つあると、後のほうの印が振り直され、もう一度承認することになります
- 承認のあとで**添付を差し替えると、キーが合わなくなってエラー**になります。キーを消して `#htmlref(demo.html)` に戻して保存し、もう一度承認してもらってください。ページや添付の名前を変えたときも同じです
- キーを同じページの別の `#htmlref` へ書き写しても構いません（キーが表すのは「管理者がそのファイル（その中身）を許可したか」だけです）

### スクリプトが動く形で開いたとき

- HTML は、Wiki とは別のオリジンとして扱われます。Wiki の cookie やログインの状態には触れません
- フォームの送信・ポップアップ・Wiki の画面への移動はできません
- 対象は**その HTML ファイル1つだけ**です。同じページの他の添付（CSS・JS・画像）を相対パスで読み込む HTML は、それらを読み込めません
- 持ち主のページを閲覧できない人には、リンクではなく「閲覧できないファイル」と表示します（[ref](/Syntax/Plugin/ref#閲覧できないページの添付ファイル) と同じです）

### 表示例

承認待ち（管理者が見たとき。管理者以外には［承認］の `<form>` が出ません）:

```html
<div class="plugin-htmlref"><a href="/.attach/このページ/demo.html" class="plugin-htmlref-file" title="25 B・2026-11-16 03:35 更新"><span class="htmlref-name">demo.html</span><span class="htmlref-kind htmlref-kind-code">コード</span><span class="htmlref-kind htmlref-kind-pending">スクリプト承認待ち</span><span class="htmlref-info">25 B・2026-11-16 03:35 更新</span></a><form class="plugin-htmlref-approve" method="post" action="/.plugin/htmlref"><input type="hidden" name="page" value="このページ"><input type="hidden" name="req" value="reqAB"><input type="hidden" name="sha" value="（添付の SHA-256）"><button type="submit" title="この HTML のスクリプトの実行を許可します（管理者）">承認</button></form></div>
```

承認済み（`#htmlref(demo.html, as_4GPjsKgOeJ, title=デモ)`）:

```html
<div class="plugin-htmlref"><a href="/.plugin/htmlref?page=このページ&amp;src=demo.html&amp;key=as_4GPjsKgOeJ" class="plugin-htmlref-file" title="25 B・2026-11-16 03:35 更新"><span class="htmlref-name">デモ</span><span class="htmlref-kind htmlref-kind-code">コード</span><span class="htmlref-kind htmlref-kind-script">スクリプト許可</span><span class="htmlref-info">25 B・2026-11-16 03:35 更新</span></a></div>
```

（大きさ・更新日時・キーは例です。）

### エラーになる書きかた

| 書きかた | 理由 |
|---|---|
| `#htmlref()` | `src` を省略した |
| `#htmlref(nosuchfile.html)` | 添付ファイルが実在しない（持ち主のページを閲覧できない人には、エラーではなく「閲覧できないファイル」になります） |
| `#htmlref(a.zip)`・`#htmlref(a.Html)`・`#htmlref(https://…)` | 添付の HTML（拡張子 `html`・`htm`・`HTML`・`HTM`）ではない |
| `#htmlref(demo.html, as_XXXXXXXXXX)` でキーが合わない | 承認のあとで添付が変わった・ページや添付の名前が変わった・キーを別のページへ書き写した。承認し直しが必要です |
| `#htmlref(demo.html, 説明書)` | 2番目以降に、印・キーの形でない値を名前無しで書いた（表示する文字は `title=説明書`） |

詳しくは [共通の書きかた](/Syntax/Common#うまく動かないとき) を参照してください。
