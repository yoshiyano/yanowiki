# calendar3 — 予定表のページに書いた予定を、月のカレンダーに並べて表示する

| 使える記法 | |
|---|---|
| ブロック `#calendar3()` | ○ |
| インライン `&calendar3();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

予定を1つのページ（予定表）に箇条書きで書いておくと、それを月のカレンダーの升目に並べて表示します。
`<<`・`>>` で前後の月へ移れます（ページ全体は読み込み直さず、カレンダーだけが入れ替わります）。

## 引数

| 引数 | 意味 | 省略したとき |
|---|---|---|
| `page` | 予定を書いたページ | `予定表` |
| `date` | 表示する年月（6桁の `yyyymm`） | 今月 |

## 予定の書きかた（予定表のページ）

次の3つの書きかたを、同じページの中で混ぜて使えます。行の頭の `- ` と `-- ` は半角で、
そのあとに空白（スペースかタブ）を1つ以上入れます。見出しや普通の文は読み飛ばします。

```pukiwiki
- 5/22 原稿締め切り
- 7/11-12 オープンキャンパス
- 4
-- 13 prog1-1
-- 20-21 合宿
```

| 行 | 意味 |
|---|---|
| `- 月/日 予定` | その日の予定 |
| `- 月/日-日 予定` | 同じ月の中の期間（例は11日から12日） |
| `- 月` | 月だけの行。このあとの `--` の行は、この月の予定 |
| `-- 日 予定` / `-- 日-日 予定` | その月の日・期間の予定 |

- **年は、予定表のページ名の末尾の4桁の数字**です（`schedule2026` なら2026年）。末尾が数字でなければ今年です
- 月に13以上を書くと翌年です（`- 14/25 模擬講義` は翌年の2月25日）
- 期間は月末を越えて続けられます（`- 1/30-33` は1月30日〜2月2日。60日目まで）
- 予定の文字には、予定表のページと同じ記法（太字・`&color(){};`・リンクなど）が使えます
- `::` のあとに書いた文字は、マウスを重ねたときに出る説明になります。説明の中の `\n` は改行です
  （`- 6/6 学科別懇談会::3年次担当\n竹内・矢野`）

予定表のページを閲覧できない人には、予定を表示しません（表題に「予定表を閲覧する権限がありません」と出ます）。

## 書きかた

予定表 `schedule2026` に次のように書いてあるとき、

```pukiwiki
- 9/7 会議::13:00から\n第1会議室
- 9/24-25 &color(red){学会};
```

```pukiwiki
#calendar3(schedule2026, 202609)
```

生成されるHTML（`Top` のページに置いた場合。予定の無い日は省略しています）:

```html
<div class="calendar3-frame" data-calendar3-page="Top" data-calendar3-api="/.plugin/calendar3">
<table class="calendar calendar3 style_calendar">
 <thead>
  <tr><th class="style_td_caltop2" colspan="7"><a href="/Top?plugin=calendar3&amp;file=schedule2026&amp;date=202608" data-calendar3-file="schedule2026" data-calendar3-date="202608">&lt;&lt;</a> <strong>2026.9</strong> <a href="/Top?plugin=calendar3&amp;file=schedule2026&amp;date=202610" data-calendar3-file="schedule2026" data-calendar3-date="202610">&gt;&gt;</a><br>[<a href="/schedule2026">schedule2026</a>]</th></tr>
  <tr><th class="style_td_week">日</th>…<th class="style_td_week">土</th></tr>
 </thead>
 <tbody>
  …<td class="style_td_day"><strong>7</strong><div class="calendar3-items">・<span title="13:00から
第1会議室">会議</span><br></div></td>…
  …<td class="style_td_day"><strong>24</strong><div class="calendar3-items">・<span style="color:red">学会</span><br></div></td>…
 </tbody>
</table>
</div>
```

## エラーについて

| 書きかた | エラーの内容 |
|---|---|
| `#calendar3(schedule2026, 2026-09)` | 年月（6桁の yyyymm）の指定が正しくありません: 2026-09 |
| `#calendar3(.hidden)` | ページ名が正しくありません: .hidden |

予定表のページがまだ無いときは、予定の無いカレンダーになります（エラーにはなりません）。
書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
