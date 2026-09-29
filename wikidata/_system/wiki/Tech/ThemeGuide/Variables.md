# テンプレートで使える変数

テーマのテンプレートには、次の値が渡されます（`themes.render_theme`）。

**ページとWiki**

| 変数 | 内容 |
|---|---|
| `site_title` | サイト名（`theme.site_title`） |
| `page_title` | ページタイトル（1行目のh1から取り出したもの。無ければページ名） |
| `farm` | Wiki名 |
| `page` | ページパス |
| `themefile` | いま使っているテーマ名（cookieで選ばれたもの → ページの指定 → `theme.name` の順で決まる） |
| `content` | 本文のHTML |
| `toc` | 目次データ `[{level, id, title}, ...]` |
| `topic_path` | TopicPathの階層データ `[{label, url}, ...]`。`url` が `None` なら現在地でリンクなし |
| `menu1` / `menu2` | `theme.menu1_page`（既定: `mainmenu`）・`theme.menu2_page`（既定: `submenu`）のHTML。該当ページが無い・読めないときは空。`theme.menu3_page` のように番号を足せば `menu3` 以降も渡る |
| `menu1_mode` / `menu2_mode` | その枠を狭い画面で畳むか（`auto`）開いたままにするか（`fix`）。`theme.menu1_mode` などで、ページごとに決まる |
| `editing` / `title_note` | そのページを誰かが編集の途中（一時保存を預かっている）か。テーマはタイトルの脇に `{{ title_note }}` を出す |
| `source_mtime` | 平文ファイルの最終更新日時（`2026-09-24 12:34`）。ふつうのページだけ |
| `render_ms` | 本文の変換にかかった時間（ミリ秒）。ふつうのページだけ |

**URL**

| 変数 | 内容 |
|---|---|
| `base_url` | URL接頭辞（`server.prefix` とWiki指定を含む）。`/=Wiki名` でアクセスしていた場合、既定のWikiでもその明示を保持する（詳細は [設計方針](/Tech/DesignPolicy) を参照） |
| `theme_url` | テーマ資材のURL接頭辞（例: `/.theme`） |
| `search_url` | 検索ページのURL（例: `/.search`） |
| `edit_url` | 編集の送り先の接頭辞（`base_url` と同じ）。`{{ edit_url }}/{{ page }}` へ `cmd=edit` をPOSTすると編集画面が開く |
| `login_url` | ログインの入口 `/.login`。**いま開いているページが `?back=` として付き**、ログイン後にそのページへ戻る。ページの権限の対象ではない（[ページの中でログインする](/Tech/LoginPlugin#ログインの入口-login) 参照） |

各URLの形は [リファレンス](/Tech/Reference/EditEntry#テーマに渡すurl) にもまとめてあります。

**編集とメニュー**

| 変数 | 内容 |
|---|---|
| `common_menu` | 全テーマ共通のメニュー（ログイン・トップ・編集・新規）のHTML。下の「共通メニュー」を参照 |
| `editable` | 編集の入口を出してよいか。**見ている人がそのページを編集できないとき**（未ログイン・権限なし）や検索画面などでは false（[編集の入口は権限で出し分ける](/Tech/Reference/EditEntry#編集の入口は権限で出し分ける) 参照） |

**フッタ**

| 変数 | 内容 |
|---|---|
| `version` | wikiSystemの版と改訂（`Ver 0.49 Rev 7.1` の形）。[ファイル構成](/Tech/ThemeGuide/Files#バージョン表示テーマ作成時の必須埋め込み) を参照 |
| `copyright_year` | いまの年（著作権表示向け） |
| `login_as` | いま入っている人の表示（`Logged in as 山田太郎`）。**未ログインなら空文字** |
| `disk_usage` | そのWikiが使っている場所（ページと添付）。下の「使用量の表示」を参照 |

**検索**

| 変数 | 内容 |
|---|---|
| `query` / `mode` / `target` / `path_filter` | 検索フォームの現在値。ふつうのページでは既定値（`query` だけは、検索結果から来たときに `?q=` の値が入る） |
| `terms` / `results_block` | 検索画面（`search.html`）だけに渡る、検索語と結果のHTML |

**プラグイン**

| 変数 | 内容 |
|---|---|
| `plugin_styles` / `plugin_scripts` | このページで使われたプラグインのCSS・JSのURL一覧。`base.html` を継承するテーマでは `base.html` が読み込むので、書かなくてよい。一から書くテーマは `<head>` で、テーマ自身のCSSより前に読み込む（`{% for url in plugin_styles %}…{% endfor %}`） |

テンプレート内のリンクには必ず `base_url` を前置します（`{{ base_url }}/UsageGuide`）。
サブパス設置（`server.prefix`）や別のWikiの閲覧時にも正しいURLになります。

目次はデータのまま渡すので、階層表示・折りたたみ・深さの制限はテンプレート側で決められます。
`toc` の `level` は、そのページで最も浅い見出しを1とした相対的な深さです（章を `#` で書いても `##` で書いても同じ字下げになります）。

## 共通メニュー（`common_menu`）

ログイン・トップ・編集・新規の4項目を、本体が組み立てて渡します（`themes.common_menu_html`）。
`{{ common_menu }}` と置けば、どのテーマでも同じ項目・動きになります。全体は `<span class="common-menu">`、
各項目は `.command`、区切りは `.command-sep` です。

- 「編集」「新規」は `editable` が真のときだけ出ます
- 「編集」は、そのページの通常URLへ `cmd=edit` をPOSTするフォームです。
  `data-hotkey="edit"`（Alt+E）が付きます
- 「新規」は、ページ名を訊くダイアログ（`.new-page-dialog`）を開きます

## 誰で入っているかの表示（`login_as`）

フッタ向けの文字列で、`Logged in as 山田太郎` のように出来上がった形で渡されます
（表示名が無ければログインID）。未ログインなら空文字なので、空かどうかで出し分けます。

```jinja
{% if login_as is defined and login_as %}<span class="login-as">{{ login_as }}</span>{% endif %}
```

`is defined` は、この変数を渡さない古い本体でも壊れないようにするためです（`disk_usage`・`render_ms` も同じ）。

文言は、フッタのほかの項目（`Convert-time`・`Last-modified`・`DiskUsage`・`Powered by`）に揃えて英語です。
日本語で出すには、テーマ側で `login_as` を使わずに組み立て直します（表示名だけを渡す変数は、いまはありません）。

## 使用量の表示（`disk_usage`）

そのWikiが使っている場所を、フッタなどに出せます。

| 書きかた | 出るもの |
|---|---|
| `{{ disk_usage.text }}` | `DiskUsage: Page/Attached 1.2MB/349KB` |
| `{{ disk_usage }}` | `1.2MB/349KB` |
| `{{ disk_usage.page }}` | `1.2MB` |
| `{{ disk_usage.attached }}` | `349KB` |
| `{{ disk_usage.page_bytes }}` | `1210736`（整形前のバイト数） |
| `{{ disk_usage.attached_bytes }}` | `356876` |

並びや言葉を変えたいときは `page` と `attached` を組み立て、条件で色を変えるなどには
`page_bytes` / `attached_bytes` を使います。

数えるのは `wiki/` 以下のページと `attach/` 以下の添付だけで、バックアップ・一時保存・アクセスログは
含みません（編集者が消して減らせるものだけを数えるため）。単位は `B`/`KB`/`MB`/`GB` から選ばれ、
10未満のときだけ小数第1位まで出ます（`465B`・`43KB`・`1.2MB`・`123MB`）。

フォルダを数えるのは、テンプレートが実際に値を使ったときだけです（結果は60秒使い回します）。
