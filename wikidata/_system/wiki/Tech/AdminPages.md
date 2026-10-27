# 管理の画面

使いかたは [管理者権限でできること](/AdminGuide) にあります。このページは仕組みの説明です。

管理ツールは **`/.admin`**（ツールの一覧の画面）から開き、新しいツールもその下に
つなぎます。一覧の中身（`adminui.TOOLS`）は、`#login` プラグインの「管理者メニュー」
タブにも出ます。

**一覧は、中身（HTML）も見た目（CSS）も本体が1か所で持ちます**（Wiki設計者の指示、
2026-10-12。「ページの二重管理にならないようにしてください。二重管理にならないなら
.admin/ ページは消す必要ありません」）。`/.admin` の画面も、タブも、同じ関数
（`adminui.admin_tools_html`）が作った一覧を差し込むだけです。見た目は
`accounts.css` で、一覧が `<link>` ごと連れてくるので、差し込む側（`#login` の
`plugin/login.css`）は一覧の見た目を持ちません。「開ける」「権限がありません」の
印も、どちらも本人に与えられた権限で出し分けます。

#img(ツールの一覧の画面（/.admin）>admin-tools.png)

| 画面 | 開ける人 | 理由・中身 |
|---|---|---|
| `/.admin` | 管理者と助手 | ツールを並べるだけ |
| `/.admin/staffperms` | **管理者だけ** | 助手に与える権限を決める。助手に許すと自分に権限を足せてしまうので、設定できない（下の「助手の権限」） |
| `/.admin/accounts` | **既定は管理者だけ**（助手に許せる） | 他人のパスワードを書き換えられる＝そこから管理者になれてしまう（[アカウントの仕組み](/Tech/Accounts)）。許しても管理者のアカウントは助手には触れない |
| `/.admin/approvals` | 管理者と助手 | 承認待ちのアカウントを承認する・断る（[アカウントの仕組み](/Tech/Accounts) の「承認制の動き」） |
| `/.groups?tab=edit&group=staff` | 管理者と助手 | 助手グループの出し入れ（下の「助手グループ」） |
| `/.groups` | ログインしていれば誰でも | ふつうのグループ（[グループ管理](/Tech/Groups)）。一覧では印 `adminui.EVERYONE` で、助手の権限に関わらずリンクにする |
| `/.admin/configwiki` | 管理者と助手 | 設定を変えられるが、管理者にはなれない（[Wikiの設定](/Tech/ConfigWiki)） |
| `/.admin/privileges` | 管理者と助手 | ページごとのアクセス制限（[ページごとの権限](/Tech/PagePermissions)） |
| `/.updatePageAuth` | 誰でも（1時間に10回まで。管理者と助手は除く） | 機能していない `#readauth`・`#writeauth` の記録を消す（[ページごとの権限](/Tech/PagePermissions/Privileges#機能していない記録の後始末updatepageauth)）。開くとすぐ行う。一覧では `adminui.EVERYONE` |
| `/.admin/stafflog` | **既定は管理者だけ**（助手に許せる） | 助手の操作の記録を見る・元に戻す（[助手の操作の記録](/Tech/StaffLog)） |
| `/.admin/operations` | 管理者と助手 | 途中で止まった名前の変更・移動を見る・続きを行う（[リネームの仕組み](/Tech/RenamePage#止めて続きから再開する)） |
| `/.admin/themes/` | 管理者と助手 | テーマのファイルを扱う。既定では助手は Jinja2 の sitetheme を扱えない（下の「テーマのファイル」） |
| `/.garbagecollect` | 管理者と助手 | 削除したページの添付を `/trashbox` へ集める。GETで確認、POSTで実行（[削除したページの添付を集める仕組み](/Tech/GarbageCollect)） |

**既定の線引きは「そこから管理者になれてしまうか」です。** 新しいツールもこの基準で
既定を振り分けます。表の「開ける人」は、助手の権限を何も決めていないときの状態で、
助手に許す・許さないは管理者が決められます（下の「助手の権限」）。判定する関数は
`sysui.require`（その画面に必要なプリンシパル `auth.ADMIN_ONLY`／`auth.STAFF`／`auth.ANY_USER`
を渡す）と、助手の権限で決める `sysui.require_perm` です。

通れないときの断りの画面（403）には、ログインの入口（`/.login`）とトップページへのリンクを出します。
「ログインしていない」と「権限がない」を分けて伝えないため、文言とリンクはログインの状態に
かかわらず同じです。ログインのあとは、そのWikiのトップへ戻ります（システムの画面は戻り先にしません）。

起点Wikiでしか開けないツール（Wikiの作成・削除・一覧・再起動）も、同じ一覧に並べます。別のWikiの一覧から押したときは、
Wiki名の付かないサイトの根のURLへ向けます（Wiki名付きのURLは403になるため）。一覧（`/.allwiki`）は設定 `farm.allwiki` が空なら並べません。

`/.admin` の一覧では、開けないツールも隠さず「管理者だけ」「権限がありません」と印を付けて並べます
（隠すと「無い」のか「開けない」のかが分からないため）。

アカウントと設定の画面の旧URL（`/.accounts`・`/.configwiki`）、助手グループの旧画面
（`/.admin/staff`）は残していません。

## 助手グループ

助手は、管理者の権限が要る画面を代わりに使えます。ただし既定では「管理者だけ」の画面は
使えません（管理者が許せば使えます。下の「助手の権限」）。

助手グループの名前は **`staff`** で、[ユーザーが自分で作れるグループ](/Tech/Groups)
そのものです（専用の画面・表は持ちません）。出し入れは `/.admin` の一覧の
「助手グループ」から `/.groups?tab=edit&group=staff` を開いて行います。

    そのグループの編集権 … g:<グループ名>, admin, g:staff の誰か
    staffグループの編集権 … admin と、`groups.staff` を与えた助手（既定では助手全員）

**`staff` がふつうのグループと違うのは、削除時の挙動だけです**（Wiki設計者の指示、
2026-09-12）。

- Wiki作成時・`initusers` 実行時に、`admin` を1人加えた状態であらかじめ作ります。
  「すでにある名前は作れない」という通常の決まりで、作り直せなくなります
- 全員が抜けたときは、次に参照されたときに `admin` だけを含む状態へ自動で戻します

`g:XXXX` という書きかたと、それを展開する `wikilib.auth.expand_principal` は
[権限は「プリンシパル」のリストで表す](/Tech/Groups#権限はプリンシパルのリストで表す)
にまとめてあります（[ページごとの権限](/Tech/PagePermissions)の許可者も同じ書きかた）。

## 助手の権限

助手に使わせる操作は、**管理者が助手ごと・操作ごとに決められます**。画面は **`/.admin/staffperms`**
（管理者だけ。`wikilib.staffpermsui`）、権限の定義・保存・判定は `wikilib.staffperms` です。
使いかたは [助手の権限](/AdminGuide/StaffPerms) にあります。

#img(助手の権限の画面（/.admin/staffperms）>/AdminGuide/StaffPerms/staffperms.png)

Wiki設計者の指示（2026-10-07）:
「admin に助手に与える権限を設定するページを作成。現在、admin と区別した権限が一括で与えられているが、
これを見直し。admin にのみ与えた権限も助手に設定できるように。デフォルトは今の状態。
それぞれ項目を細分化し、横に助手ユーザ、縦に機能を並べた表に。助手に与える権限をチェックボックスに
マークを入れることで有効化する。」

これに沿って、次のように作りました。

- **表は横が助手、縦が機能。** 助手は `staff` グループのメンバーから管理者を除いた人。
  チェックを入れた操作だけ、その助手が使える。管理者は常にすべて使える
- **既定は、この仕組みを導入する前の状態。** 助手が使えた画面は使え、管理者だけだった画面
  （アカウント・助手の操作の記録・sitetheme）は使えない。表に何も無ければ動きは変わらない
- **管理者だけだった権限も、助手に与えられる**

### 権限の一覧

名前は `<画面>.<操作>`。画面の関門は、必要な名前を宣言して `sysui.require_perm`
（画面全体）か `auth.can`（操作ごと）で確かめます。定義は `staffperms.PERMS` にあります。

| 画面 | 権限（既定） | 効く場所 |
|---|---|---|
| アカウント（`/.admin/accounts`） | `accounts.view`（×）・`.add`（×）・`.rename`（×）・`.password`（×）・`.delete`（×） | 画面を開く・追加のフォーム・一覧のAPI（ID・名前の書き換え、パスワードの入れ直しとロック、削除） |
| 承認（`/.admin/approvals`） | `approvals.approve`（○）・`.reject`（○） | 承認・断る。どちらかがあれば画面を開ける |
| グループ（`/.groups`） | `groups.others`（○）・`groups.staff`（○） | `auth.can_edit_group`。助手グループ以外・助手グループ |
| Wikiの設定（`/.admin/configwiki`） | `config.view`（○）・`.edit`（○）・`.extrarules`（○）・`.rename`（○） | 画面を開く・API の `op`（`set`・`rx_…`・`rename`） |
| アクセス制限（`/.admin/privileges`） | `privileges.view`（○）・`.edit`（○） | 画面を開く（と `evaluate`）・API の `add`・`set`・`delete` |
| 助手の操作の記録（`/.admin/stafflog`） | `stafflog.view`（×）・`.undo`（×） | 画面を開く・元に戻す |
| 中断した操作（`/.admin/operations`） | `operations.view`（○）・`.resume`（○） | 画面を開く・続きを行う |
| テーマのファイル（`/.admin/themes/`） | `themes.view`（○）・`.slot`（○）・`.site.view`（×）・`.site.edit`（×） | 画面を開く、`mount_access`（slottheme の読み書き、sitetheme の読み取り・読み書き） |
| 削除したページの添付（`/.garbagecollect`） | `garbagecollect.run`（○） | 画面と実行 |
| 起点Wikiだけの画面 | `site.newwiki`・`.delwiki`・`.allwiki`・`.restart`（すべて○。`/.admin/update` も `site.restart` で見る） | `sysui.require_on_default_farm` |

（○は既定で助手に許す、×は許さない）

`/.admin`（ツールの一覧）は、助手なら開けます。一覧の「開けるか」の印は、同じ権限で出し分けます
（`adminui.TOOLS` の4つ目が、開くのに要る権限の名前）。

### 前提のある権限

「アカウントを消す」は一覧を見られないと意味がないので、`Perm.needs` に前提を書き、
**前提が外れていればその権限も効かない**（`staffperms.resolve`）。画面のJS（`staffperms.js`）は、
前提を外すと従属を外し、従属を付けると前提も付ける。保存時にサーバーも同じに揃える。

### クロコの実装例（設計者は未確認）

上の指示には、次の細部は含まれていません。クロコが決めたものです。

- **権限の細かさ**: 表の行（上の一覧）の区切りかた。一覧のAPIが受ける操作（書き換え・削除）と、
  画面ごとの「開く」を軸に、1つの画面を操作ごとに分けた。分けすぎ・足りないがあれば直す
- **保存は既定と違うものだけ**: `config/users.db` の `staff_perms(uidnum, perm, allowed)` に、
  既定と違う行だけを持つ。画面で既定と同じにして保存すれば行は消える。**あとから権限を足したとき、
  行を持たない助手には、その権限の既定が効く**。既定を変えれば、行を持たない全員に効く
- **保存した内容はその場で効く**（要求ごとにDBを読む。キャッシュしない）
- **助手グループから外しても、決めた権限は残る**。戻したときに前と同じ権限になる。アカウントを
  消したときは消える（番号が別の人に回ったときに引き継がないため）
- **設定の画面は管理者だけ**。助手に許すと、自分に権限を足せてしまう
- **管理者のアカウント（`uidnum = 1`）は、助手には書き換えも削除もさせない**（`accounts.can_modify`）。
  `accounts.password` を許しても、管理者のパスワードを書き換えて管理者になることはできない。
  従来の線引き（「そこから管理者になれてしまうか」）を、許したあとも保つため
- **助手のアカウント操作は、助手の操作の記録に残す**（`account.add`・`.update`・`.delete`）。
  消したアカウントは記録から戻せる（行と所属グループを控える）。書き換えの記録でも、ハッシュ値は
  画面に出さない（記録の画面は `accounts.view` が無い助手も開けるため）
- **権限を保存したことは `log/admin.log.db` に残す**（`cmd = staffperms`）。見る画面は無い
- **助手が助手を増やすと、新しい助手は既定の権限から始まる**。`groups.staff` を持つ助手は、
  自分に無い権限を持つ助手を（その人のアカウントを使える形で）作れる。画面の「注意」で伝えるだけで、
  防ぐ仕組みは持たない。`accounts.password` を持つ助手は、ほかの助手になりすませるのも同じ

### いまの限り

- `#login` プラグインの「管理者メニュー」タブは、`adminui.admin_tools_html` を `wiki_dir` なしで
  呼ぶため、**既定の権限**で開けるかの印を出す。権限を既定から変えた助手には、実際と違う印に
  なることがある（開けないツールを押しても、断りの画面になるだけ）。プラグイン側の呼び出しの
  修正は、プラグインの担当に頼む（`ChangeLogTech/System/todo`）
- 承認待ちの人数の赤字（`#login`）と `force=1` の回数制限の除外（`#updateDB`・`/.updatePageAuth`）は、
  権限ではなく「助手であること」（`auth.is_staff`）で決まる

## 見た目は共通の外枠（テーマの影響を受けない）

管理ページ（ツールの一覧・アカウント・承認・グループ・設定・Wikiの一覧・新規作成・
削除・名前変更・再起動、権限が無いときの断りの画面）は、テーマを通さず、
編集画面と同じヘッダ＋全幅の本文の外枠（`sysui.page`）で描きます。

- ページ一覧は付けません
- 色は外枠が持ち、明暗はOSの設定（`prefers-color-scheme`）に従います
- 狭くしたい画面は、その画面のCSSで `max-width` を持ちます

アクセス制限（`/.admin/privileges`）・編集画面の「履歴」タブ・競合の統合の画面は、
それぞれ独自の外枠で、`sysui.page` は使っていません（共通化は今後の課題）。

## テーマのファイル

`/.admin/themes/` は、ファイル一覧（`/.files/`）と同じ webFileDir の画面で、4つのフォルダを並べて見せます
（Wiki設計者の指示、2026-10-03。スロット型の2つは 2026-10-04「ツリーには４つ並べる」）。

| ツリーの最上位 | 中身 | 扱い |
|---|---|---|
| `common` | 全Wiki共通のテーマ（トップレベルの `theme/`） | 読み取り専用 |
| `sitetheme` | このWiki固有のテーマ（`wikidata/<Wiki名>/theme/`） | 新規作成・アップロード（CSS・画像）・テキストの編集（CSS）・コピー・名前の変更・移動・削除（ごみ箱あり） |
| `slotcommon` | 全Wiki共通の [スロット型のテーマ](/Tech/ThemeGuide/SlotTheme)（トップレベルの `slottheme/`） | 読み取り専用 |
| `slottheme` | このWiki固有のスロット型のテーマ（`wikidata/<Wiki名>/slottheme/`） | 新規作成・アップロード・テキストの編集（HTML・CSS）・コピー・名前の変更・移動・削除（ごみ箱あり） |

common の項目を選んで右クリックかツールバーの「sitetheme へコピー」を押すと、sitetheme の同じ場所へ写り、その場所が開きます（設計者の「shared から sitetheme へのコピー機能が欲しい」、2026-10-03）。
同じ名前のファイルがあれば上書きするかを尋ね、「いいえ」ならそれを飛ばして残りを写します。上書きされたファイルは sitetheme のごみ箱から戻せます。
Ctrl+C して sitetheme に貼り付ける、ドラッグする、でも写せます（こちらは写す先を自分で選びます）。
名前の `common` は、テンプレートで共通のテーマを指す `common/`（`{% extends "common/base.html" %}`）と揃えたものです（設計者の「shared ではなく common のほうが良いか？」に、クロコが賛成して変えた）。
個別Wiki固有のテーマが優先されるので（[置き場所](/Tech/ThemeGuide/Files#置き場所)）、写したものを直せば、そのWikiだけ見た目が変わります。
アップロードは、ツールバーと何も無いところの右クリックの「アップロード」、またはほかのアプリからのドロップで行います（フォルダごとも可）。
1ファイルの上限は添付と同じ `attach.max_size`（[Wikiの設定](/.admin/configwiki)）です（クロコの実装例。設定を変えたら再起動まで前の値のまま）。
CSS は、右クリックの「テキストを編集」で中身を直せます（UTF-8、1 MiB まで）。保存すると元の中身は残らない（ごみ箱にも入らない）ので、大きく直す前は common から写し直せることを頼りにしてください。

### slottheme で書けるもの

スロット型のテーマ（`.html`）と、CSS・画像（png・jpg・jpeg・gif・webp・avif・ico）・フォント（woff・woff2）だけです。
slotcommon の項目は、右クリックかツールバーの「slottheme へコピー」で、slottheme の同じ場所へ写せます。

`.html`・`.css` は、アップロード・テキストの編集・名前の変更・貼り付け・「slottheme へコピー」のどれで入るときも検査し、
描くときに取り除かれるもの（`<script>`・`onclick`・`@import`・外への `url()` など）があれば、理由を出して保存しません
（Wiki設計者が「断る」を選んだ、2026-10-05）。テキストの編集では、書いた中身を残したまま編集画面に戻ります。
描くとき・配るときにも同じものを取り除くので、ほかの経路（git など）で置かれたファイルも安全です。

### 開ける人と記録

管理者と助手が開けます（Wiki設計者の「権限は各wikiの 助手まで。記録は残します」、2026-10-04）。

| | 管理者 | 助手 |
|---|---|---|
| common | 見るだけ・「sitetheme へコピー」 | 見るだけ（コピーして slottheme に貼り付けられる） |
| sitetheme | 読み書き | 見せない |
| slotcommon | 見るだけ・「slottheme へコピー」 | 同じ |
| slottheme | 読み書き | 読み書き |

表の助手の欄は、助手の権限の既定です。管理者は [助手の権限](/AdminGuide/StaffPerms)（`wikilib.staffperms`）で、助手ごとに
slottheme の編集（`themes.slot`）を外す、sitetheme を見せる（`themes.site.view`）・編集させる（`themes.site.edit`）ことができます
（前提は `themes.view`）。使いかたは [テーマと見た目](/AdminGuide/Themes) にあります。

助手の slottheme での操作は [助手の操作の記録](/Tech/StaffLog) に残ります（管理者の操作は記録しません）。
助手に sitetheme を見せないこと、記録に「元に戻す」を付けないことはクロコの実装例です（設計者は未確認）。

以下はクロコの実装例（設計者は未確認）: ほかの拡張子のファイルは置けない（名前の変更でも）、新しいファイルは拡張子を `.css` にして作る、
ごみ箱は `pageinfo/slottheme-trash/`、マウントの名前（`slotcommon`・`slottheme`）と並び順。

### sitetheme で書けるもの

sitetheme は Jinja2 が読む場所なので、画面からコードを入れさせません（Wiki設計者の指示、2026-10-03。
「css と画像ファイルに制限して upload やファイルを編集する権限をもたせます」「html については
コピー権限までは与えても編集権限は与えません。リネームにより html から他のファイルにすることは認めても、
他のファイルから html など jinja2 がコード解釈する拡張子に変更することは不許可」）。

| 操作 | 決まり |
|---|---|
| アップロード | CSS と画像（png・jpg・jpeg・gif・webp・avif・ico）だけ |
| テキストの編集 | CSS だけ。ほかのファイルではメニューに出ない |
| 名前の変更・新規作成 | ほかの拡張子から html・js・svg など（`themefilesui.CODE_EXTS`）へは変えられない。html から別の拡張子へ、html どうしは変えられる |
| コピー | html も写せる（common から・sitetheme の中で。中身は元のまま） |

この決まりは管理者にも効きます（クロコの案を設計者が承認、2026-10-04）。

今のコードで Jinja2 が読むのは `.html` で終わる名前だけです。以下はクロコの実装例（設計者は未確認）:

- 変えられない拡張子に、閲覧者のブラウザでスクリプトとして動く `.js`・`.svg` も入れた。`/.theme/` は sitetheme のファイルを共通のものより先に配るので、書いた CSS を `base.js` へ変えられると、全閲覧者のブラウザで動くため
- アップロードできる画像から `.svg` を外した（直接開くとスクリプトが動く）

以下はクロコの実装例（設計者は未確認）:

- 「sitetheme へコピー」の写し先を同じ場所にすること、同じフォルダがあれば中身を混ぜること、「いいえ」で飛ばして残りを写すこと
- sitetheme のごみ箱は `wikidata/<Wiki名>/pageinfo/theme-trash/` に置く。`/.theme/` は「.」で始まる名前も配信するので、テーマのフォルダの中には置かない

## 実装の置き場所

| 何を | どこが |
|---|---|
| ツールの一覧の画面（`/.admin`） | `_sys/wikilib/adminui.py` |
| ツールの一覧（中身のHTML。`#login` のタブにも差し込む） | `adminui.admin_tools_html`（並びは `adminui.TOOLS`） |
| アクセス制限の画面・API | `_sys/wikilib/privilegesui.py`（資材は `_sys/privilegesui/`） |
| アクセス制限の記録（`config/privileges`） | `_sys/wikilib/privilege_records.py` |
| 助手グループ（`staff`）の判断・データ | `_sys/wikilib/groups.py`（[グループ管理](/Tech/Groups)参照） |
| 開ける人の判定（`require`。プリンシパルを渡す） | `_sys/wikilib/sysui.py` |
| 共通の外枠（`page`） | `_sys/wikilib/sysui.py`・`_sys/sysui/shell.css` |
| 権限の判断（`allows`／`is_staff`／プリンシパル展開） | `_sys/wikilib/auth.py` |
| 画面のCSS | `_sys/accounts/accounts.css`（アカウントの画面と共有） |
| 中断した操作の画面 | `_sys/wikilib/operationsui.py`（手順のファイルは `_sys/wikilib/operations.py`） |
| テーマのファイルの画面 | `_sys/wikilib/themefilesui.py`（webFileDir の読み込みと要求の受け渡しは `filesui` と共有） |
| 自動テスト | `tests/test_adminui.py`・`tests/test_groups.py`・`tests/test_privilege_records.py`・`tests/test_operations.py`・`tests/test_themefilesui.py` |
