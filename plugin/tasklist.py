"""tasklist — チェックリスト（`- [ ]`/`- [x]`）にチェックボックスを付ける。

    #tasklist(sync)

    - [ ] やること
    - [x] やったこと

Markdown記法のページで、上のように行頭へ`- [ ]`（未完了）または`- [x]`
（完了）を書くと、チェックボックス付きの一覧になります。**GFM（GitHub
Flavored Markdown）の標準的な書きかたがそのまま使えます**（チェック
リストの検出自体に呼びかたは要りません）。

 1. sync … ページのどこかにこれを書くと、チェックボックスを押した結果を
       **元のページ本文へ書き戻す**ようになります (default: 書き戻さない
       ＝チェックボックスは押せません)

**`#tasklist(sync)`と書いていないページでは、チェックボックスは押せません**
（チェックボックスの代わりに、状態だけを示すアイコンが表示されます）。
誤って触れただけで本文が書き換わってしまうことを防ぐための既定です。押して保存
できるようにしたい場合は、ページのどこか1か所に`#tasklist(sync)`と
書いてください（`#plugin_debug`のような「以降だけ」ではなく、**ページ
全体のチェックリストに効きます**）。

`sync`を書いたページでは、チェックを付けた・外したことを、あらためて
編集画面を開いて保存し直す必要はありません。

**チェックボックスを切り替えられるのは、そのページの編集の権限がある人だけ**
です。権限の無い人には、状態を示すアイコンが表示されます。

PukiWiki記法（`.txt`）のページでは使えません（GFMの書きかたなので、
Markdown記法（`.md`）のページ専用です）。
"""

""" 技術資料
Wiki設計者の指示: 「tasklistでチェックが変化したら、markdownの内容も連動して
更新する」（`Tech/ChangeLog/plugin/index.md`の「今後の予定」より）。

## `sync`（書き戻しは既定でオフ、Wiki設計者の指示2026-09-08）

当初の実装は「チェックリストがあれば常に書き戻す」だった。その後、
Wiki設計者の指示（「オプションの sync をつけた場合のみ変更をオリジナルの
テキストに反映させる。syncが無い場合は変更そのものを許可しない」）を
受けて、**`#tasklist(sync)`という明示的な呼びかたが無い限り書き戻さない
（チェックボックス自体を押せなくする）**方針に変えた。書きかた・スコープ
（ページ単位で書けばよく、書く場所は問わない／押せないときの見た目は
disabled）は、実装前にWiki設計者に確認して決めた。

その後、実際の見た目を確認したWiki設計者から「disabledのinputは色が抜けて
見えにくい。syncでないものはそもそもフォーム部品にする必要が無い。
アイコンで見せてほしい」との指摘（2026-09-08）を受け、`sync`が無い項目は
`<input disabled>`ではなく、状態だけを示す静的な`<span>`アイコンに変更した
（技術資料「JavaScript側」参照）。

## `sync`の判定は「トークンを直接見る」方式にした理由

`#tasklist(sync)`は`PLUGIN_INFO["args"]`（`flag: True`）で宣言した通常の
プラグイン呼び出しだが、**その`_convert`の戻り値・副作用は判定に使えない**。
markdown-it-pyのパイプラインは「まず`engine.core.ruler`が全トークンを
組み立て（`plugin_block`トークンもここで作られる）、そのあとで
`engine.renderer.render()`がトークンを上から順に描画しながら初めて
`_convert`を呼ぶ」という2段構成（`_sys/wikilib/plugins.py`の
`register_plugin_rules`が`engine.add_render_rule("plugin_block", ...)`
でレンダー規則として登録しているのがその証拠）。`_mark_lines`は
`engine.core.ruler.after("github-tasklists", ...)`で**パース段階**に
差し込んだ関数なので、そのページの`#tasklist(sync)`はまだ`_convert`を
呼ばれておらず、`plugin_debug.py`のように「先に呼ばれたプラグインが
`context`にフラグを立て、後続の`_convert`がそれを読む」という順序に
乗れない（`plugin_debug`が有効なのは、フラグを立てる側も読む側も両方
**レンダー段階**で動くため）。

そこで`_tokens_declare_sync(tokens)`が、`_convert`を経由せず**トークン
列そのもの**（`plugin_block`タイプ・`meta["name"] == "tasklist"`・
`meta["args"].strip() == "sync"`）を直接調べる。`plugin_block`トークンは
パース段階（`plugin_block_rule`、`fence`より手前に差し込まれている）で
既に作られているため、`_mark_lines`の時点で確実に読める。`args`の
妥当性検証（`sync`以外の値を書いたときのエラー表示）は、この判定とは
別に`_convert`が呼ばれたときの通常のプラグインエラー経路がそのまま
処理する（`_tokens_declare_sync`は単に「一致しなければ無効」として
黙って書き戻し無効側に倒すだけでよい。ミスタイプはページ上に赤い
エラー枠として別途表示されるため、判定側で二重にエラーを出す必要が
無い）。

## 元々の実装との関係

このファイルは元々、`mdit_py_plugins.tasklists.tasklists_plugin`を
`enabled=True`（チェックボックスを`disabled`にしない）で読み込むだけの
薄いラッパーだった。`enabled=True`自体は最初から効いていたため、
押すとブラウザの既定動作でチェックの見た目は変わっていたが、**ページを
再読み込みすると元に戻る**（本文へは何も書き戻していない）状態だった。
このファイルの実装は、それに「押した結果を本文へ書き戻す」経路を
足したもの。本家PukiWikiに同名のプラグインはあるが、書式も設計も
まったく別物（本家はプラグイン記法`#tasklist`で別ページの状況を集計する
もの）のため、ここでは互換対象として扱っていない。

## チェックボックスをJavaScriptで組み立てる理由（`allow_html`との関係）

`tasklists_plugin`は、チェックボックスを`<input class="task-list-item-
checkbox" ...>`という**生HTML**（`html_inline`トークン）として挿し込む。
ところがこのシステムは、PukiWiki記法・Markdown記法を問わず生HTML
トークン（`html_block`/`html_inline`）をすべて`allow_html`の方針で
一律に濾す設計になっている（`_sys/wikilib/htmlpolicy.py`の`install()`。
「PukiWiki側のパーサーも同じトークン型を出すので、この2つを差し替えれば
両方の記法に効く」との同ファイルのdocstringどおり、記法によらず一律）。
`markdown.allow_html`の既定値は`false`（`config/default.yaml`）のため、
**既定設定のままでは、tasklistのチェックボックスは実際の`<input>`に
ならず、エスケープされた文字列（`&lt;input ...&gt;`）としてそのまま
表示されてしまう**。これは今回の実装で気づいた、`tasklists_plugin`を
素朴に使うだけでは避けられない、このシステム独自の制約である。

**このチェックボックスは、`allow_html`が本来防ごうとしている「ページ
著者が本文に自由に書き込んだ生HTML」ではない。** 中身は固定テンプレート
（`type="checkbox"`と、ページパス・行番号・状態・APIのURLという、
いずれも本文の文字列ではなくシステム側（`context`）が持つ値）で、
利用者が`- [ ] 文字列`のように書ける「文字列」の部分（`first`/`second`
等の表示テキスト）はチェックボックス側の属性には一切入らない。つまり
**ページ著者が書いた文字列を経由してこのHTML片の構造を変える手段が
無い**（`allow_html`が警戒している「本文にHTMLを混ぜて任意の要素・
属性を注入される」という状況が構造的に起こり得ない）。この性質が
あるからこそ、`allow_html`の枠外で描いても安全と判断できる（`allow_html`
の値を見ずに済ませてよいという結論は、この性質から導かれるもので、
Wiki設計者の指示から導かれるものではない）。

その上で、実装の手段としては2案あった:

1. tasklistのチェックボックスだけ`allow_html`の対象外にする
   （`htmlpolicy.py`側に例外を設ける。wikiSystem側との調整が必要）
2. `allow_html`に関わらず常に表示されるよう、**チェックボックスの見た目
   自体をJavaScriptで組み立てる**（wikiSystem（`_sys/`）を一切触らない）

どちらも安全性の結論（上記）は変わらず、**wikiSystem本体を編集するか
どうかという実装場所の違い**でしかない。Wiki設計者の判断は2（Wiki設計者の指示、
2026-09-04：「allow_htmlに関わらず常にチェックボックスを表示します。
実装はjavascriptに生成させる方針で、wikiSystemを一切触らないものです」）。

そのため、**サーバー側ではチェックボックスの生HTMLをそもそも描かせない**
（`_mark_lines`が`tasklists_plugin`の挿し込んだ`html_inline`トークンを
`children.pop(0)`で取り除く）。代わりに必要な情報（ページ・行番号・
現在のON/OFF・書き戻し先URL）を、**構造化トークンである`<li>`自身の
属性**（`data-page`/`data-line`/`data-checked`/`data-api`。
`Token.attrSet`）として持たせる。`<li>`のクラス・属性は`renderAttrs`
という別の描画経路（`RendererHTML`の通常のトークン描画で、`escapeHtml`
により値は自動でエスケープされる）で出力され、**`html_inline`/
`html_block`向けの`allow_html`フィルタの対象に一切ならない**
（`htmlpolicy.install()`が差し替えるのは`html_block`/`html_inline`の
描画規則だけで、`list_item_open`のような構造トークンの属性描画には
関与しない）。実測で、`Token.attrSet`した値がクォート・山括弧・
アンパサンドを含んでいても正しく`&quot;`/`&lt;`/`&gt;`/`&amp;`へ変換
されて出力されることを確認済み（`allow_html`の設定に関係なく常に安全。
なお`data-page`/`data-api`の値自体もシステム側の`context.page`/
`context.base_url`から来ており、利用者が本文に書ける文字列ではない）。

チェックボックスそのものの見た目・状態管理・保存への送信は、すべて
`plugin/tasklist.js`が受け持つ（後述）。

## どの行を書き換えるかの特定（`register(engine)`とtoken.map）

`tasklists_plugin`は`md.core.ruler.after("inline", "github-tasklists", ...)`
で、パース済みのトークン列（`state.tokens`）を書き換えてチェックボックス
のHTMLを差し込む。書き換え対象はトークンだけで、**どの行から生まれた
項目かという情報はどこにも残らない**。

`code.py`が`register(engine)`（`PLUGIN_INFO`方式とは別の、markdown-it-py
本体を直接拡張する窓口。`code.py`の技術資料参照）で描画規則を差し替えた
のと同じ仕組みを、ここでは**もう1つcoreルールを追加する**形で使う。
`engine.core.ruler.after("github-tasklists", "tasklist-line-map", _mark_lines)`
で、`tasklists_plugin`の直後に自前のルールを差し込み、`<li>`（`list_item_
open`トークン）へ`data-*`属性を付ける。

値は`list_item_open`トークンの`.map[0]`（0始まりの開始行）をそのまま使う。
`_sys/wikilib/render.py`の`heading_positions`/`section_range`が見出しの
位置特定に使っているのと同じ`token.map`で、**そのページの生ソース
（`render_source`に渡された`text`そのもの）上の行番号**と一致することを
実測で確認した（`- [ ] 項目`のような行のmapは`[開始行, 終了行)`のうち
開始行が必ずその行そのものを指す。チェックボックスの記号`[ ]`/`[x]`は
リスト項目の先頭行にしか書けないため、複数行にまたがる項目でも
`.map[0]`はチェックボックスのある行と一致する）。

`.map`を取り出す位置は`tokens[i-2]`（`is_todo_item`と同じ位置関係。
`tasklists_plugin`のソースにある`is_todo_item`/`todoify`の実装をそのまま
踏襲し、`list_item_open`のクラスに`"task-list-item"`が付いているかで
対象を選ぶ）。現在のON/OFF（`data-checked`）は、取り除く前の`html_inline`
トークンの内容に`checked="checked"`が含まれるかで判定する（除去する
直前の、まだ生HTML文字列として残っている段階で読み取る）。

`data-page`は`state.env["wiki"]`（`PluginContext`。`render_source`が
`env = {"wiki": context}`で渡す）の`context.page`から取る。トップレベルの
ページ表示だけでなく、`ls.py`の`ajaxview`が読み込むフラグメント
（`_action`が別ページ用の`sub = PluginContext(..., page=pagepath, ...)`を
新しく作って描画する）や`include.py`の差し込み先でも、それぞれ自分の
`PluginContext`を新しく作って描画し直す設計になっているため、
チェックリストが「今ブラウザで開いているページ」とは別のページの中身
だった場合でも、書き戻し先を取り違えない。

## `context.used_plugins`への追加（資材読み込み）

`plugin/tasklist.css`・`plugin/tasklist.js`は、他の多くのプラグインと
同じく`context.used_plugins`に名前が入っているページだけに読み込まれる
（`_sys/wikilib/themes.py`）。ふつうは`#pluginname(...)`という呼びかたが
あって初めて`call_plugin`が`context.used_plugins.add(name)`する
（`_sys/wikilib/plugins.py`）が、**tasklistには呼びかた自体が無い**
（GFM標準の`- [ ]`をそのまま使うだけ）ため、その経路を素通りする。

`code.py`は「中身を省略した`#code()`という空呼び出しを、資材読み込みの
合図として使う」という手当てをしたが、tasklistには合図となる呼びかたが
そもそも無いので同じ手は使えない。代わりに、**`_mark_lines`が実際に
チェックリストの項目を1つでも見つけた時点で、その場で
`context.used_plugins.add("tasklist")`する**（該当箇所参照）。パース時に
「このページにチェックリストがあるかどうか」がちょうど判明する場所
なので、`#code()`のような空呼び出しの合図を利用者に書いてもらう必要が
無く、かつチェックリストが無いページでは資材を読み込まずに済む
（コード上の必要最小限の追加で済んだ）。

## PukiWiki記法（`.txt`）では効かない理由

`_sys/wikilib/render.py`の`parse_source`は、PukiWiki記法のページを
`engine.parse(text, env)`（markdown-it本体）ではなく
`wikilib.pukiwiki.parse(text, ...)`という完全に別の独自パーサーに通す。
`tasklists_plugin`も本ファイルの`_mark_lines`も`engine.core.ruler`に
積んだフックであり、`pukiwiki.parse`の経路は素通りする。つまり
PukiWiki記法のページでは`- [ ]`は最初から特別扱いされず、ただの
リスト項目の文字列（`[ ] 文字列`）として表示される。GFMのタスクリストは
元々Markdown固有の拡張なので、これは互換性の欠落ではなく素直な
スコープ（本家PukiWikiの`#tasklist`とは別物であることは冒頭の説明の
とおり）。

## `_action`（書き戻し）

`/.plugin/tasklist`へのPOSTで、`page`（ページパス）・`line`（0始まりの
行番号。`data-line`をそのまま返す）・`checked`（新しい状態、`"1"`/`"0"`）
を受け取る。

状態の変更を伴う操作なので、`updateDB.py`（冪等な取り込みなのでGETも
許した）とは違い**POSTのみ**を受け付ける（GETでの誤発火・先読みで
チェック状態が変わってしまうのを避けるため）。

**`sync`が無いページからのPOSTは、ここで独立に確かめて断る。** JS側で
`data-api`を付けない（後述）ことでボタン自体を押せなくしているが、それは
見た目の制御に過ぎず、`/.plugin/tasklist`へは誰でも直接POSTできてしまう。
「対象行が本当にチェックリストの項目か」を毎回読み直して確かめている
のと同じ理由（クライアント側の状態を信用しない）で、書き換える直前に
**そのページの現在の本文**を`_text_declares_sync`で確かめ、`#tasklist(sync)`
が無ければ`PluginArgumentError`にする。`_text_declares_sync`は
`wikilib.render.parse_source`でトークン化するだけ（`_convert`を呼ぶ完全な
描画はしない）で`_tokens_declare_sync`に渡す——`_mark_lines`と同じ関数を
使い、判定基準を1か所に保つ。生テキストを正規表現で直接走査する案も
検討したが、フェンスコード内に書かれた説明用の`#tasklist(sync)`（この
プラグイン自身のSyntax/Plugin文書が典型）まで誤検出する恐れがあるため
採らなかった（`parse_source`はブロック解析を経るので、フェンス内は
最初から対象に入らない）。

書き戻す本文は、DBではなく**平文ファイル（`resolve_page_ref`が返す
`ref.body`）**から読む。DBの内容を基準にすると、システムを経由しない
直接編集や取り込み前の変更が書き戻しで消えてしまう（`pagesave.py`の
docstring「差分の基準はDBの内容」は**バックアップ差分の基準**の話で、
書き換える対象の本文そのものはここでは常に最新の平文ファイルを使う。
`save_page`呼び出し時の`known`は省略し、差分の基準は従来どおりDBに
任せている）。

対象行が本当にチェックリストの項目か（`_TASK_LINE_RE`）を毎回確かめて
から書き換える。行番号がずれる・対象行が変わっている（ページが
その間に別の変更を受けた）場合は書き換えず`PluginArgumentError`にする。
チェックの現在値（ON/OFFどちらだったか）は確かめない（`checked`の指す
新しい状態へ単純に上書きする）。理由は2つ:

- 通信の間に他の変更（そのチェックボックス以外の書き換え）が入っても、
  「このチェックボックスをこの状態にしたい」という要求は変わらないため、
  古い状態と食い違っていてもエラーにする理由が無い
- 同じチェックボックスを立て続けに何度もクリックした場合の連続リクエスト
  も、最終的に届いた状態が反映されればよく（枚挙的な整合性チェックは
  過剰）、単純な上書きの方が挙動を説明しやすい

保存は`wikilib.pagesave.save_page`（保存の3点セット：バックアップ・
平文ファイル書き出し・DB反映を1か所にまとめた共通処理。`pagesave.py`の
docstring参照）にそのまま任せる。このプラグイン独自の保存ロジックは
持たない（`updateDB.py`が`pagesync.sync_wiki`を素通りさせているのと
同じ考えかた）。

## 権限（Wiki設計者の指示、2026-09-25）

**チェックを切り替えられるのは、そのページの編集の権限（`W`）がある人だけ。**
同じ「本文を書き換えるプラグイン」でも、`#comment`・`#vote`は編集の権限が
無い人も使える（閲覧できれば通す）のと扱いを分けた。以前（2026-09-15〜）は
tasklistも閲覧できれば通していた。

- `_action`は`context.privilege.check(page) != PAGE_WRITE`なら403
- `_mark_lines`は、見ている人に`W`が無ければ`sync`のページでも`data-api`を
  付けず、代わりに`data-noauth`を付ける（JSは押せないアイコンを出し、
  `title`で理由を「編集の権限が無い」と出し分ける）。見た目の制御に過ぎず、
  守りは`_action`の側
- 描画は閲覧者ごとに行われる（本文HTMLを閲覧者をまたいでキャッシュしない）
  ので、見ている人ごとに出し分けてよい

## JavaScript側（`plugin/tasklist.js`）

`_mark_lines`が生HTMLの`<input>`を取り除いた結果、サーバー側が返す
`<li class="task-list-item" data-page="…" data-line="…" data-checked="…"
[data-api="…"]>項目の文字列</li>`には、チェックボックスの見た目が一切無い
（技術資料「チェックボックスをJavaScriptで組み立てる理由」参照）。
`plugin/tasklist.js`が`li.task-list-item[data-line]`をすべて拾い、
`data-api`があれば`document.createElement("input")`で実際の
チェックボックス要素を（`.checked`は`data-checked`から）、無ければ状態を
示す絵文字の`<span>`を、それぞれ先頭に差し込む（詳しくは後述）。
`allow_html`の設定に一切左右されない（サーバーから届く生HTML・
エスケープ済み文字列のどちらにも依存しない、常に同じ1本の経路）。

`data-api`は`sync`が有効なページでしか付けない（`_mark_lines`参照）。
JS側は`li.dataset.api`が無ければ、そもそも`<input>`を作らず、状態
（`data-checked`）だけを示す絵文字を`<span class="task-list-item-icon">`
に入れて差し込む。**当初は`disabled`な`<input>`にしていたが、実際の
見た目を確認したWiki設計者から「disabledのinputは色が抜けて見えにくい。
syncでないものはそもそもフォーム部品にする必要が無い」との指摘
（2026-09-08）を受けて変更した。** 一度SVGアイコン（`currentColor`で
テーマ追随）案も試したが、Wiki設計者の指示（「icon画像にはemojiを利用」、
2026-09-08）で絵文字（✅/⬜）に差し替えた——絵文字は自前の色を持つため、
`currentColor`より確実に、かつSVGを書かずに視認性を確保できる。
`title`属性で理由を一言添える（フォーム部品ではなくなったため
`disabled`起因の見た目上の制約は無いが、押せない理由を伝える手段として
残した）。

`<ul>`側の弾丸記号を消す`.contains-task-list { list-style: none; }`は
`theme/base.css`/`theme/bloom.css`に既にあり（`tasklists_plugin`の
`class`付与は`_mark_lines`より前の`fcn`がそのまま行っているため変更
無し）、JavaScriptで組み立てたチェックボックスもそのまま行頭に収まる。

チェックボックスの`change`イベントで`data-api`（`/.plugin/tasklist`）へ
POSTする。保存に失敗したら**チェックボックスの見た目を元に戻す**
（ブラウザの既定動作で先に切り替わった状態を打ち消す）。モーダルや
アラートは出さず、該当の`<li class="task-list-item">`へ
`task-list-item-error`クラスを一瞬（2秒）だけ付けて赤い枠で知らせる
だけにした（`plugin/tasklist.css`）。ネットワーク断・ページが消えた等の
失敗は稀で、チェックの状態は見た目からすぐ分かる（元に戻る）ため、
それ以上の説明は過剰と判断した。
"""

import re

from bottle import request
from mdit_py_plugins.tasklists import tasklists_plugin

from wikilib.auth import PAGE_WRITE
from wikilib.pagesave import save_page
from wikilib.paths import PLUGIN_URLPATH, farm_plugin_dir, is_valid_pagepath, resolve_page_ref
from wikilib.plugins import PluginArgumentError, build_markdown_renderer
from wikilib.render import parse_source
from wikilib.web import plain

PLUGIN_INFO = {
    "help": "#tasklist(sync)",
    "args": [
        {"name": "sync", "flag": True, "default": False},
    ],
}

# 書き換え対象の行かどうかの判定。リストの記号（-/+/*、または "1." 等の
# 番号付き）のあとにチェックボックスが続く行の先頭にだけマッチする。
# group(1) が「チェックボックスより前」（記号・空白）で、書き換えるときは
# ここは変えずに [ ]/[x] の部分だけ差し替える。
_TASK_LINE_RE = re.compile(r"^([ \t]*(?:[-+*]|\d+[.)])[ \t]+)\[[ xX]\](?=[ \t]|$)")


def _tokens_declare_sync(tokens):
    """トークン列に`#tasklist(sync)`の呼び出し（`plugin_block`トークン）が
    含まれるか。`_convert`を経由しない判定である理由は技術資料
    「`sync`の判定は『トークンを直接見る』方式にした理由」を参照。"""
    for token in tokens:
        if token.type != "plugin_block":
            continue
        meta = token.meta or {}
        if meta.get("name") == "tasklist" and (meta.get("args") or "").strip() == "sync":
            return True
    return False


def _text_declares_sync(context, text, ext):
    """本文を独立に解析し直して`#tasklist(sync)`の有無を確かめる
    （`_action`用。技術資料「`_action`（書き戻し）」参照）。"""
    engine = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir), context)
    tokens = parse_source(engine, text, ext, {"wiki": context})
    return _tokens_declare_sync(tokens)


def _convert(resolved, body, context):
    # このプラグイン自身は何も出力しない。`sync`が有効かどうかは
    # `_mark_lines`（パース段階）が独立に判定するため、ここでは何もしない
    # （技術資料「`sync`の判定は『トークンを直接見る』方式にした理由」参照）。
    return ""


def _mark_lines(state):
    """タスクリストの項目から、`tasklists_plugin`が挿し込んだ生HTMLの
    チェックボックス（`html_inline`トークン）を取り除き、代わりに
    `<li>`自身（構造化トークン）へ`data-page`/`data-line`/`data-checked`/
    （`sync`が有効なら）`data-api`を付ける。チェックボックスの見た目
    そのものは`plugin/tasklist.js`がこの属性を読んでJavaScriptで組み立てる
    （技術資料「チェックボックスをJavaScriptで組み立てる理由」参照）。"""
    context = (state.env or {}).get("wiki")
    if context is None:
        return

    page = context.page or ""
    api = f"{context.base_url}/{PLUGIN_URLPATH}/tasklist"
    sync = _tokens_declare_sync(state.tokens)
    # 見ている人に編集の権限が無ければ、sync のページでも押せない形で出す
    # （技術資料「権限」。押しても _action が403で断る）
    writable = sync and context.privilege.check(page) == PAGE_WRITE
    found = False

    tokens = state.tokens
    for i in range(2, len(tokens) - 1):
        li = tokens[i - 2]
        if li.type != "list_item_open" or not li.map:
            continue
        if "task-list-item" not in (li.attrGet("class") or "").split():
            continue
        if tokens[i - 1].type != "paragraph_open" or tokens[i].type != "inline":
            continue
        children = tokens[i].children or []
        if not children:
            continue
        checkbox = children[0]
        if checkbox.type != "html_inline" or "task-list-item-checkbox" not in checkbox.content:
            continue

        checked = "1" if 'checked="checked"' in checkbox.content else "0"
        children.pop(0)  # 生HTMLの<input>は描かせない（技術資料参照）。以降はJS側の役目

        found = True
        li.attrSet("data-page", page)
        li.attrSet("data-line", str(li.map[0]))
        li.attrSet("data-checked", checked)
        if writable:
            li.attrSet("data-api", api)
        elif sync:
            li.attrSet("data-noauth", "")  # 押せない理由を出し分けるための印（tasklist.js）

    if found:
        context.used_plugins.add("tasklist")


def register(engine):
    engine.use(tasklists_plugin, enabled=True)
    engine.core.ruler.after("github-tasklists", "tasklist-line-map", _mark_lines)


def _action(context):
    if request.method != "POST":
        raise PluginArgumentError("この操作はPOSTでのみ受け付けます。")
    if not context.wiki_dir:
        raise PluginArgumentError("Wikiが特定できません。")

    page = (request.forms.getunicode("page", "") or "").strip("/")
    if not page or not is_valid_pagepath(page):
        raise PluginArgumentError("ページの指定が正しくありません。")

    try:
        line_no = int(request.forms.get("line", ""))
    except (TypeError, ValueError):
        raise PluginArgumentError("行番号の指定が正しくありません。")

    checked = request.forms.get("checked", "") in ("1", "true")

    # 編集の権限（W）が無ければ書き込ませない（Wiki設計者の指示、2026-09-25）。
    # 技術資料「権限」参照。使いかたの誤りではないので PluginArgumentError（400）
    # ではなく403で返す
    if context.privilege.check(page) != PAGE_WRITE:
        return plain("このページを編集する権限がありません。", status=403)

    ref = resolve_page_ref(context.wiki_dir, page)
    if ref is None or not ref.exists:
        raise PluginArgumentError("このページはまだありません。")

    if not _text_declares_sync(context, ref.body, ref.ext):
        raise PluginArgumentError(
            "このページには #tasklist(sync) が書かれていないため、チェックの変更は保存できません。")

    lines = ref.body.splitlines(keepends=True)
    if not (0 <= line_no < len(lines)):
        raise PluginArgumentError("該当する行が見つかりません（ページが変わった可能性があります）。")

    m = _TASK_LINE_RE.match(lines[line_no])
    if not m:
        raise PluginArgumentError("指定された行はチェックリストの項目ではありません（ページが変わった可能性があります）。")

    mark = "x" if checked else " "
    lines[line_no] = m.group(1) + f"[{mark}]" + lines[line_no][m.end():]
    text = "".join(lines)

    save_page(context.wiki_dir, context.config, ref.subpath, ref.ext, text, path=ref.path)
    return plain("OK")
