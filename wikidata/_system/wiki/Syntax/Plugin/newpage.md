# newpage — ページ名を入れて新しいページを作る入力欄を置く

| 使える記法 | |
|---|---|
| ブロック `#newpage()` | ○ |
| インライン `&newpage();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

#code()

ページ名の入力欄とボタンを置きます。名前を入れてボタンを押すと、

- そのページが**まだ無ければ、すぐに新規作成の編集画面**が開きます
- **もう在れば、そのページ**が開きます

PukiWikiの `newpage` の移植で、PukiWikiで書いた `#newpage()`・`#newpage(./)`・`#newpage(フォルダ/)` はそのまま動きます。
作る先のフォルダの一覧を入力欄の下に並べる `showlist` と、入力欄の前の文字・ボタンの文字・入力例を変える指定を足してあります。

## 書きかた

### このページの下に作る

入力欄に最初から `./` を入れておきます。続けて名前を入れると、このページの下にページができます
（`演習` のページで `./第02回` と入れれば `演習/第02回`）。

```pukiwiki
#newpage(./)
```

生成されるHTML（`演習` のページに置いた場合）:

```html
<form class="newpage" method="post" action="/.plugin/newpage">
 <div>
  <input type="hidden" name="cmd" value="edit">
  <input type="hidden" name="refer" value="演習">
  <label for="_p_newpage_1">ページ新規作成:</label>
  <input type="text" name="page" id="_p_newpage_1" value="./" size="30" required>
  <input type="submit" value="編集">
 </div>
</form>
```

### 決まったフォルダの下に作る

```pukiwiki
#newpage(研究情報/)
```

入力欄に `研究情報/` が入った状態で表示されます。

### 作る先の一覧も並べる（`showlist`）

`showlist` を書くと、入力欄の下に、`page` で指定したフォルダの下のページの一覧が出ます。
次の2つは同じ表示になります（一覧の中身・並び・見せかたは [ls](/Syntax/Plugin/ls) と同じです）。

```pukiwiki
#newpage(研究情報/)
#ls(研究情報/)
```

```pukiwiki
#newpage(研究情報/, showlist)
```

生成されるHTML（一覧の項目は例です。実際には、そのときのページ構成で決まります）:

```html
<form class="newpage" method="post" action="/.plugin/newpage">
 <div>
  <input type="hidden" name="cmd" value="edit">
  <input type="hidden" name="refer" value="演習">
  <label for="_p_newpage_1">ページ新規作成:</label>
  <input type="text" name="page" id="_p_newpage_1" value="研究情報/" size="30" required>
  <input type="submit" value="編集">
 </div>
</form>
<nav class="ls" data-ls-api="/.plugin/ls"><ul class="ls-list"><li class="ls-page"><a href="/研究情報/Kinect">Kinect</a></li><li class="ls-page"><a href="/研究情報/VR">VR</a></li></ul></nav>
```

`#newpage(./, showlist)` なら、このページの下の一覧です。`page` を省くときは、`#newpage(, showlist)` のように1番目を空けてください
（`#newpage(showlist)` と書くと、`showlist` が入力欄に入れておくページ名として扱われます）。

一覧は、入力欄を出さないとき（[下記](#表示されない場合)）も出します。`#ls` を並べて書いた場合と同じです。

### 表示の文字を変える

```pukiwiki
#newpage(./, label=レポートを作る, button=作成, placeholder=第01回)
```

生成されるHTML:

```html
<form class="newpage" method="post" action="/.plugin/newpage">
 <div>
  <input type="hidden" name="cmd" value="edit">
  <input type="hidden" name="refer" value="演習">
  <label for="_p_newpage_1">レポートを作る:</label>
  <input type="text" name="page" id="_p_newpage_1" value="./" size="30" required placeholder="第01回">
  <input type="submit" value="作成">
 </div>
</form>
```

1ページにいくつ置いても構いません（入力欄の `id` は `_p_newpage_1`、`_p_newpage_2`… と振られます）。

## 引数

| 番号 | 名前 | 意味 | 既定 |
|---|---|---|---|
| 1 | `page` | 入力欄に最初から入れておくページ名（**1番目に固定**） | 空 |
| 2 | `showlist` | 単語を書くと、入力欄の下に `page` の下のページの一覧を出す | 出さない |
| 3 | `label` | 入力欄の前の文字（`label=値` の形でのみ） | `ページ新規作成` |
| 4 | `button` | ボタンの文字（`button=値` の形でのみ） | `編集` |
| 5 | `placeholder` | 入力欄が空のときに薄く出す例（`placeholder=値` の形でのみ） | 出さない |

入れた名前（と `page`）は、本文のリンク `[[ページ名]]` と同じ決まりで、**このページから見て**解決されます。

| 入れた名前 | 意味（`演習/第01回` に置いた場合） |
|---|---|
| `abc` / `/abc` | `abc`（Wikiの先頭から） |
| `./abc` | `演習/第01回/abc`（このページの下） |
| `../abc` | `演習/abc`（1つ上から） |
| `[[abc]]` | `abc`（角括弧は外して扱います） |

## 表示されない場合

次のときは、入力欄そのものを出しません。

- このページを編集できない閲覧者が見ている（未ログインの人も含む。[ページごとの権限](/Tech/PagePermissions)）

このとき `showlist` を書いていれば、**一覧だけ**が出ます。`#newpage(研究情報/, showlist)` は、
編集できない閲覧者には `#ls(研究情報/)` とまったく同じ表示になります（ページを作れる人には入力欄と一覧、
見るだけの人には一覧だけ、という使い分けが1行でできます）。`showlist` が無ければ、何も表示されません。

作る先のページを編集できない場合は、ボタンを押した先の編集画面で断られます。

## エラーについて

| 書きかた | エラーの内容 |
|---|---|
| `#newpage(研究情報/, foo)` / `#newpage(./, 作る)` | 引数の解釈に失敗しました（2番目に書けるのは `showlist` だけ。`label` などは `label=作る` の形で書きます） |

`showlist` の一覧の側で起きたエラー（フォルダの指定が正しくない等）は、[ls](/Syntax/Plugin/ls) と同じ表示になります。

ボタンを押したとき、入れた名前に `=` や `.` で始まる部分が含まれている（ページとして作れない名前）と、
「ページ名が正しくありません」と表示されます。入力欄を空のまま押すことはできません。

書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
