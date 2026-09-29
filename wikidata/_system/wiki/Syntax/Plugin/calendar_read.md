# calendar_read — ページがある日だけリンクにしたカレンダーを表示する

| 使える記法 | |
|---|---|
| ブロック `#calendar_read()` | ○ |
| インライン `&calendar_read();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

[calendar](/Syntax/Plugin/calendar) を「read」のモードで表示します。PukiWikiの `calendar_read` の移植です。
引数・日ごとのページの名前（`日記/20260925`）・見た目は calendar と同じです。

その日のページが**閲覧できるときだけ**、日付がリンクになります。表題には `(read)` と出ます。
[calendar](/Syntax/Plugin/calendar) の既定と同じ表示です。

## 書きかた

```pukiwiki
#calendar_read(日記, 202609)
```

生成されるHTMLは calendar と同じ形で、表題が `<strong>2026.9 (read)</strong>` になります。

## エラーについて

[calendar](/Syntax/Plugin/calendar#エラーについて) と同じです。
