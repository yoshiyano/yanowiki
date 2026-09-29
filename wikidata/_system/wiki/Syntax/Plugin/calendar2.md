# calendar2 — 前後の月へ移れるカレンダーと、今日のページの中身を並べて表示する

| 使える記法 | |
|---|---|
| ブロック `#calendar2()` | ○ |
| インライン `&calendar2();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

日記や作業記録に使うカレンダーです。日ごとのページは `日記/2026-09-25` の形の名前です。
カレンダーの右には、今日のページの中身を表示します。PukiWikiの `calendar2` の移植です。

- ページがある日は、日付がそのページへのリンクになります
- まだ無い日は、押すとそのページの新規編集の画面が開きます（編集の権限がある人だけ。無い人には数字だけ）
- `<<`・`>>` で前後の月へ移れます（ページ全体は読み込み直さず、カレンダーと今日のページの中身だけが入れ替わります。
  JavaScriptが動かない環境では、このページを月を指定して開き直します）
- 今日のページがあれば、その中身と「[この日記を編集]」ボタンを右に出します。無ければ「〜は空です。」と出し、
  「〜」（ページ名）を押すとそのページの新規編集の画面が開きます（編集の権限が無い人には、ページ名は文字だけです）。
  別の月を表示しているときは、その月の1日のページが対象です
- 閲覧できないページは、無いページと同じに扱います

たまった日ごとのページをまとめて読むときは [calendar_viewer](/Syntax/Plugin/calendar_viewer) を使います。

## 引数

| 引数 | 意味 | 省略したとき |
|---|---|---|
| `page` | 日ごとのページを置く場所のページ名。`*` なら、ページ名の頭に何も付けない（`2026-09-25`） | このページ |
| `date` | 表示する年月（6桁の `yyyymm`） | 今月 |
| `off` | これを書くと、今日のページの中身を出さない | 出す |

引数はどの順で書いてもかまいません。

## 書きかた

```pukiwiki
#calendar2(日記)
```

生成されるHTML（`Top` のページに置いた場合。途中の週と今日のページの中身は省略しています）:

```html
<div class="calendar2-frame" data-calendar2-api="/.plugin/calendar2" data-calendar2-page="Top" data-calendar2-file="日記" data-calendar2-off="0">
<div class="calendar2">
<div class="calendar2-month">
<table class="calendar style_calendar">
 <thead>
  <tr><th class="style_td_caltop" colspan="7"><a href="/Top?plugin=calendar2&amp;file=%E6%97%A5%E8%A8%98&amp;date=202608" data-calendar2-date="202608">&lt;&lt;</a> <strong>2026.9</strong> <a href="/Top?plugin=calendar2&amp;file=%E6%97%A5%E8%A8%98&amp;date=202610" data-calendar2-date="202610">&gt;&gt;</a><br>[<a href="/%E6%97%A5%E8%A8%98">日記</a>]</th></tr>
  <tr><th class="style_td_week">日</th>…<th class="style_td_week">土</th></tr>
 </thead>
 <tbody>
  <tr><td class="style_td_blank"></td><td class="style_td_blank"></td><td class="style_td_day"><form class="calendar-new small" method="post" action="/%E6%97%A5%E8%A8%98/2026-09-01"><input type="hidden" name="cmd" value="edit"><button type="submit" title="日記/2026-09-01">1</button></form></td>…</tr>
  …
  <tr>…<td class="style_td_today"><a href="/%E6%97%A5%E8%A8%98/2026-09-25" title="日記/2026-09-25"><strong>25</strong></a></td>…</tr>
  …
 </tbody>
</table>
</div>
<div class="calendar2-today">
（日記/2026-09-25 の中身）
<hr><form class="calendar2-edit" method="post" action="/%E6%97%A5%E8%A8%98/2026-09-25"><input type="hidden" name="cmd" value="edit"><button type="submit" class="small">[この日記を編集]</button></form>
</div>
</div>
</div>
```

`off` を書いたときは、枠（`calendar2-frame`）の中が `<table class="calendar style_calendar">…</table>` だけになります。

## エラーについて

| 書きかた | エラーの内容 |
|---|---|
| `#calendar2(日記, メモ)` | ページ名は1つだけ書いてください: 日記,メモ |
| `#calendar2(.hidden)` | ページ名が正しくありません: .hidden |

今日のページがこのページ自身などで、すでに差し込み済みのときは「既に差し込み済みのページです」と出ます。
書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
