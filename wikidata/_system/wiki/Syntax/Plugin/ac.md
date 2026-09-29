# ac — 押すと開いたり閉じたりする、折りたたみの枠を作る

| 使える記法 | |
|---|---|
| ブロック `#ac()` | ○ |
| インライン `&ac();` | ○ |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

長い手順や補足を畳んでおき、見出しを押したときだけ中身を見せます。PukiWikiで使われていた
`ac`（kanateko氏作）の書きかたがそのまま使えます。見た目と作りは新しくしてあり、JavaScriptが
無くても開け閉めでき、キーボードでも操作できます。ページ内検索（Ctrl+F）では、閉じた中身の文字も見つかります。

## 引数

書く順は自由です（`#ac(alt,h)` も `#ac(h,alt)` も同じ）。

| 引数 | 意味 | インライン |
|---|---|---|
| 見出しの文字 | 押すところに出す文字。書かなければ「…」。太字や色などの記法も使える | ○ |
| `h` | 見出しの文字を書かず、**すぐ上にある見出し**（段落など）を押すところにする | × |
| `open` | 最初から開いておく | ○ |
| `alt` | 閉じているあいだ「▴ クリック or タップで詳細を表示」と添える | ○ |
| `all` | 中身を書かず、「全て開く／全て閉じる」ボタンを置く | × |
| `end` | 中身を書かず、`all` のボタンが効く範囲をここで終える | × |

## 書きかた

### 見出しを付けて畳む

```pukiwiki
#ac(設定手順は以下の通り。){{
+ 手順1
+ 手順2
}}
```

生成されるHTML（`id` は呼び出しごとに変わります）:

```html
<details class="plugin-ac" id="ac-2a62fbc0"><summary class="plugin-ac-summary"><span class="plugin-ac-icon" aria-hidden="true"></span><span class="plugin-ac-title">設定手順は以下の通り。</span></summary>
<div class="plugin-ac-body">
<ol>
<li>手順1</li>
<li>手順2</li>
</ol>
</div>
</details>
```

### すぐ上の見出しで開け閉めする（`h`）

見出しの下の一部だけを畳みます。見出しを押す（またはTabで選んでEnter・Space）と開きます。

```pukiwiki
*Windows 関連
#ac(h){{
#newpage(win/)
}}
#ls(win/)
```

生成されるHTML（`#newpage` の中身は省略しています）:

```html
<h2 id="windows-関連">Windows 関連</h2>
<details class="plugin-ac" id="ac-9ea41dee" data-ac-head="prev"><summary class="plugin-ac-summary"><span class="plugin-ac-icon" aria-hidden="true"></span><span class="plugin-ac-title">…</span></summary>
<div class="plugin-ac-body">
（#newpage の入力欄）
</div>
</details>
```

見出しはその場に残るので、目次や見出しからの編集はそのまま使えます。押すところにした見出しは、中身と離れないよう、
上の余白がふつうの見出しの1/4に、下の余白が0になります。JavaScriptが動かない環境では、
見出しの代わりに「…」を押して開きます。

### まとめて開く（`all`・`end`）

`#ac(all)` から後ろ、次の `#ac(all)` か `#ac(end)` までにある折りたたみを、ボタン1つで全部開け閉めします。

```pukiwiki
#ac(all)
#ac(1つめ){{
一つ目の中身
}}
#ac(2つめ){{
二つ目の中身
}}
#ac(end)
```

`#ac(all)` の生成されるHTML（ボタンはJavaScriptが動くときだけ見えます）:

```html
<div class="plugin-ac-ctrl" hidden><button type="button" class="plugin-ac-all">全て開く</button></div>
```

対象が全部開いているとボタンは「全て閉じる」に変わります。

### 文の途中で畳む（インライン）

```pukiwiki
文中の &ac(補足){説明の中身}; です。
```

生成されるHTML:

```html
文中の <span class="plugin-ac-inline"><input type="checkbox" class="plugin-ac-check" id="ac-610a2fcf"><label class="plugin-ac-label" for="ac-610a2fcf"><span class="plugin-ac-icon" aria-hidden="true"></span>補足</label><span class="plugin-ac-inline-body">説明の中身</span></span> です。
```

## エラーについて

| 書きかた | エラーの内容 |
|---|---|
| `#ac(h)` | 折りたたむ中身を {{ }} の中に書いてください。 |
| `#ac(見出し,h){{ … }}` | h（すぐ上の見出しを使う）と見出しの文字は一緒に書けません。 |
| `&ac(h){x};` | h はインライン（&ac）では使えません。（`all`・`end` も同じ） |
| `&ac(見出し){};` | 折りたたむ中身を { } の中に書いてください。 |

書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
