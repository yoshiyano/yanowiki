# calendar_viewer — calendar・calendar2 で作った日ごとのページの中身を、まとめて表示する

| 使える記法 | |
|---|---|
| ブロック `#calendar_viewer()` | ○ |
| インライン `&calendar_viewer();` | × |

呼びかたのルールは [共通の書きかた](/Syntax/Common#プラグインの呼びかた) をご覧ください。

[calendar2](/Syntax/Plugin/calendar2) などで作った日ごとのページ（`日記/2026-09-25`）の中身を、日付の見出しを付けて
続けて表示します。日記や作業記録を1ページで読むのに使います。PukiWikiの `calendar_viewer` の移植です。

- 見出しは `2026/9/25 (金)` の形です。編集の権限があればそのページの編集画面を開くボタン、無ければページへのリンクです
- 最後に、前後の月（`<<2026-10`・`2026-08>>`）や前後の件（`<<前の5件`・`次の5件>>`）へのリンクを出します
- 閲覧できないページは並びません
- 長い記事は7行ほどで畳まれ、「（省略）」を押すと続きが開きます。開いたあとは「（閉じる）」で畳み直せます（JavaScriptが動かない環境や印刷では全文です）

## 引数

| 引数 | 意味 | 省略したとき |
|---|---|---|
| `page` | 日ごとのページを置いた場所のページ名。空なら、ページ名の頭に何も付けない日付のページ（calendar2 の `*`） | 頭に何も付けない |
| `range` | どのページを出すか（下の表） | 省略できません |
| `mode` | 出す範囲と並べる順（下の表） | `past` |
| `date_sep` | 日付の区切り文字。calendar のページ（`20260925`）を出すときは `none` | `-` |

| `range` | 出すページ |
|---|---|
| `this` | 今月 |
| `2026-09` | その年月 |
| `5` | 先頭から5件 |
| `5*5` | 先頭から数えて5件目（0が先頭）から5件 |

| `mode` | 出す範囲と順 |
|---|---|
| `past` | 今日と過去を、新しい順に（日記・記録向け） |
| `future` | 今日と未来を、古い順に（予定向け） |
| `view` | 過去から未来まで全部を、古い順に |

## 書きかた

```pukiwiki
#calendar_viewer(日記, this)
```

生成されるHTML（`日記` のページに置き、編集の権限がある人が見た場合。本文は省略しています。長い記事の「（省略）」ボタンは、ブラウザで表示したときに付きます）:

```html
<h1 class="calendar_viewer-title"><form class="calendar_viewer-edit" method="post" action="/%E6%97%A5%E8%A8%98/2026-09-25"><input type="hidden" name="cmd" value="edit"><button type="submit">2026/9/25 (金)</button></form></h1>
<div class="calendar_viewer-body">
（日記/2026-09-25 の中身）
</div>
<h1 class="calendar_viewer-title"><form class="calendar_viewer-edit" method="post" action="/%E6%97%A5%E8%A8%98/2026-09-24"><input type="hidden" name="cmd" value="edit"><button type="submit">2026/9/24 (木)</button></form></h1>
<div class="calendar_viewer-body">
（日記/2026-09-24 の中身）
</div>
<div class="calendar_viewer"><span class="calendar_viewer_left"><a href="/%E6%97%A5%E8%A8%98?plugin=calendar_viewer&amp;mode=past&amp;file=%E6%97%A5%E8%A8%98&amp;date_sep=-&amp;date=2026-10">&lt;&lt;2026-10</a></span><span class="calendar_viewer_right"><a href="/%E6%97%A5%E8%A8%98?plugin=calendar_viewer&amp;mode=past&amp;file=%E6%97%A5%E8%A8%98&amp;date_sep=-&amp;date=2026-08">2026-08&gt;&gt;</a></span></div>
```

予定のページを今日から先の順に並べるときは `#calendar_viewer(予定, this, future)`、
[calendar](/Syntax/Plugin/calendar) で作ったページ（`日記/20260925`）なら `#calendar_viewer(日記, this, past, none)` と書きます。

## エラーについて

| 書きかた | エラーの内容 |
|---|---|
| `#calendar_viewer(日記)` | 表示する範囲（2つ目の引数）を指定してください。 |
| `#calendar_viewer(日記, きのう)` | 2つ目の引数が正しくありません: きのう（this・yyyy-mm・件数・x*件数 のどれか） |
| `#calendar_viewer(日記, this, all)` | モード（3つ目の引数）の指定が正しくありません: all（past / view / future） |
| 同じページ名の calendar_viewer を5つ以上 | 同じページ名（日記）の calendar_viewer は4つまでです。 |

置いたページ自身が一覧に入るときは、「このページ自身は差し込めません」と出して飛ばします。
書きかた自体が壊れている場合は、共通のエラーになります（[共通の書きかた](/Syntax/Common#うまく動かないとき) 参照）。
