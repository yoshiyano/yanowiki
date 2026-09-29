# calendar_edit — 全部の日付をリンクにしたカレンダーで、日ごとのページを作りながら使う

| 使える記法 | |
|---|---|
| ブロック `#calendar_edit()` | ○ |
| インライン `&calendar_edit();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

[calendar](/Syntax/Plugin/calendar) を「edit」のモードで表示します。PukiWikiの `calendar_edit` の移植です。
引数・日ごとのページの名前（`日記/20260925`）・見た目は calendar と同じです。

**すべての日付を押せます。** まだ無い日を押すと、その日のページの新規編集の画面が開くので、
日記や記録のページを作りながら使えます（編集の権限が無い人には、ページへのリンクです）。表題には `(edit)` と出ます。

## 書きかた

```pukiwiki
#calendar_edit(日記, 202609)
```

生成されるHTMLは calendar と同じ形で、表題が `<strong>2026.9 (edit)</strong>` になります。
まだ無い日は、その日のページへ `cmd=edit` を送るボタンです（`<form class="calendar-new" method="post" action="/%E6%97%A5%E8%A8%98/20260901"><input type="hidden" name="cmd" value="edit"><button type="submit" title="日記/20260901"><strong>1</strong></button></form>`）。ある日は、その日のページへのリンクです。

## エラーについて

[calendar](/Syntax/Plugin/calendar#エラーについて) と同じです。
