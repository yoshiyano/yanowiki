# calendar — 1か月のカレンダーを表示し、日ごとのページへ案内する

| 使える記法 | |
|---|---|
| ブロック `#calendar()` | ○ |
| インライン `&calendar();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

1か月のカレンダーを表示します。日ごとのページ（`日記/20260925` のように、区切りの無い8桁の日付）が
**ある日だけ**、日付がそのページへのリンクになります。PukiWikiの `calendar` の移植です。

- ページを作りながら使うときは [calendar_edit](/Syntax/Plugin/calendar_edit)（全部の日がリンクになります）
- 日ごとのページを `日記/2026-09-25` の形にしたいときは [calendar2](/Syntax/Plugin/calendar2)
- 日ごとのページの中身をまとめて読むときは [calendar_viewer](/Syntax/Plugin/calendar_viewer)（`date_sep=none` を付けます）

## 引数

| 引数 | 意味 | 省略したとき |
|---|---|---|
| `date` | 表示する年月（6桁の `yyyymm`） | 今月 |
| `page` | 日ごとのページを置く場所のページ名 | このページ |

年月とページ名は、どちらの順で書いてもかまいません。

## 書きかた

```pukiwiki
#calendar(日記, 202609)
```

生成されるHTML（途中の週は省略しています）:

```html
<table class="calendar style_calendar">
 <thead>
  <tr><th class="style_td_caltop" colspan="7">
   <strong>2026.9 (read)</strong><br>
   [<a href="/%E6%97%A5%E8%A8%98">日記</a>]
  </th></tr>
  <tr><th class="style_td_week">日</th><th class="style_td_week">月</th>…<th class="style_td_week">土</th></tr>
 </thead>
 <tbody>
  <tr><td class="style_td_blank"></td><td class="style_td_blank"></td><td class="style_td_day"><strong>1</strong></td>…<td class="style_td_sat"><strong>5</strong></td></tr>
  …
  <tr>…<td class="style_td_today"><a href="/%E6%97%A5%E8%A8%98/20260925" title="日記/20260925"><strong>25</strong></a></td>…</tr>
  …
 </tbody>
</table>
```

- 表題の `(read)` は表示のモードです（[calendar_edit](/Syntax/Plugin/calendar_edit) では `(edit)`）
- 日曜は `style_td_sun`、土曜は `style_td_sat`、今日は `style_td_today` です。クラス名はPukiWikiと同じです
- 閲覧できないページは、無いページと同じに扱います（リンクになりません）

## エラーについて

| 書きかた | エラーの内容 |
|---|---|
| `#calendar(foo, bar)` | 年月（6桁）とページ名を1つずつ書いてください: foo,bar |
| `#calendar(.hidden)` | ページ名が正しくありません: .hidden |

6桁でない数字（`#calendar(20260)`）は、年月ではなくページ名として扱います（PukiWikiと同じ）。

書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
