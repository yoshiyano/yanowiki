# attachls — ページに添付されたファイルの一覧を出す

| 使える記法 | |
|---|---|
| ブロック `#attachls()` | ○ |
| インライン `&attachls();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

#code()

ページに添付されたファイルを一覧にして並べます。書いたページの添付だけでなく、ページ名を指定して別のページの添付も並べられます。
1つ1つのファイルは、[ref](/Syntax/Plugin/ref) の `noimg` と同じ見せかた（種別の札と、大きさ・更新日時つきのリンク）で並べます。
画像もリンクとして並べ、`showimg` を書いたときだけ、その場に表示します。

## 書きかた

### このページの添付ファイルを並べる

```pukiwiki
#attachls()
```

添付を追加・削除すれば、一覧も自動で変わります（添付は編集画面の「添付ファイル」タブで管理します）。

### 別のページの添付ファイルを並べる

```pukiwiki
#attachls(資料)
#attachls(./配布物)
```

ページ名は本文のリンク `[[ページ名]]` と同じ決まりです（裸の名前はWikiの先頭から、`./` はこのページの下、`../` は1つ上から）。

### 並び順・見せかたを変える

```pukiwiki
#attachls(資料, MTIME_REV)        新しい順
#attachls(資料, showimg)              画像はその場に表示して並べる
#attachls(, showimg, 120x90)         このページの添付を、画像は小さく表示して
```

ページ名の後ろは、好きな順に書けます。ページ名を省いて後ろだけ書くときは、`#attachls(, showimg)` のように1番目を空けます。

実際の表示（[アカウントの仕組み](/Tech/Accounts) のページの添付。上が既定、下が `showimg` で画像を小さく表示した例）:

```pukiwiki
#attachls(Tech/Accounts)
#attachls(Tech/Accounts, showimg, 160x100)
```

#attachls(Tech/Accounts)

#attachls(Tech/Accounts, showimg, 160x100)

生成されるHTML（`資料` のページに `a.pdf` と `b.png` が添付されている場合の例）:

```html
<ul class="attachls">
<li class="attachls-item"><a href="/.attach/資料/a.pdf" class="plugin-ref-file" title="120.5 KB・2026-09-25 10:00 更新"><span class="ref-name">a.pdf</span><span class="ref-kind ref-kind-pdf">PDF</span><span class="ref-info">120.5 KB・2026-09-25 10:00 更新</span></a></li>
<li class="attachls-item"><a href="/.attach/資料/b.png" class="plugin-ref-file" title="45.2 KB・2026-09-25 10:05 更新"><span class="ref-name">b.png</span><span class="ref-kind ref-kind-image">画像</span><span class="ref-info">45.2 KB・2026-09-25 10:05 更新</span></a></li>
</ul>
```

各行の中身は、`&ref(資料/a.pdf, noimg);`・`&ref(資料/b.png, noimg);` と書いたときの出力そのものです
（`showimg` を書くと `noimg` を付けずに渡すので、`b.png` は `&ref(資料/b.png);` と同じく画像になります）。

## 引数

| 番号 | 名前 | 意味 | 既定 |
|---|---|---|---|
| 1 | `page` | 添付ファイルを並べるページ（**1番目に固定**） | このページ |
| 2 | `sort` | 並び順。`FNAME`: ファイル名 / `MTIME`: 更新日時 / `SIZE`: 大きさ。`_REV` を付けると逆順（`MTIME_REV` で新しい順） | `FNAME` |
| 3 | `showimg` | 単語を書くと、画像をその場に表示する | 表示せず、ファイル名のリンクにする |
| 4 | `noimg` | 書いても何も変わらない（既定と同じ。`showimg` と両方書いたら `showimg` が効く） | — |
| 5 | `noicon` | 単語を書くと、種別の札を出さない | 出す |
| 6 | `nolink` | 単語を書くと、画像を画像そのものへのリンクにしない（`showimg` のときだけ効く） | リンクにする |
| 7 | `size` | 画像の大きさ（`showimg` のときだけ効く）。`120x90` / `120x` / `x90` / `120w` / `90h` / `50%` | 元の大きさ |

`noicon`・`nolink`・`size` は [ref](/Syntax/Plugin/ref) と同じ意味です。

## 一覧を出さないとき

| 場合 | 表示 |
|---|---|
| 添付ファイルが1つも無い | 添付ファイルはありません: /ページ名 |
| そのページを閲覧する権限が無い（[ページごとの権限](/Tech/PagePermissions)） | このページを閲覧する権限がありません: /ページ名（ファイル名も出しません） |

一覧に出るかどうかは、**そのページを閲覧できるかどうか**だけで決まり、添付ファイルを開けるかどうかと必ず一致します。
編集の権限は要りません（閲覧だけできる人や、ログインしていない人にも、読めるページの一覧は出ます）。
フォルダの入口ページは、`#attachls(Tech)` と書いても `#attachls(Tech/index)` と書いても同じページ（`Tech`）として扱います。

## エラーについて

このプラグイン固有のエラーです。

| 書きかた | エラーの内容 |
|---|---|
| `#attachls(.hidden)` | ページの指定が正しくありません（`=` や `.` で始まる部分を含む名前） |
| `#attachls(資料, BAD)` | 引数の解釈に失敗しました（`sort` の候補や `noimg` などのどれにも当てはまらない） |
| `#attachls(資料, size=big)` | 大きさの指定が正しくありません |

書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
