"""ls — ページの一覧を作り、それぞれへのリンクを並べるプラグイン。

    #ls()                              自分の下のフォルダを一覧にする
    #ls(Tech)                          指定したフォルダ
    #ls(Tech, recursive)               下の階層まで辿る
    #ls(Tech, recursive, MTIME_REV)    並び順も指定
    #ls(Tech, ajaxview, format_md=TITLE)  folderの後ろは好きな順で好きなだけ書ける
    #ls(Tech, exclude=old)             old を含む名前を除外

 1. **folder** … 対象のフォルダ（1番目に固定。省略すると自分の下）
       Tech も /Tech もwikiの先頭から、
       ./Tech は今のページの下、../Tech は1つ上から
       （本文のリンク [[Tech]] とまったく同じ決まりです）
 2. recursive  … 単語を書くと下の階層まで辿る (default: 辿らない)
 3. sort       … 並び順 (default: FNAME)
       FNAME(_REV): ファイル名 / MTIME(_REV): 更新日時
       / TITLE(_REV): タイトル / SIZE(_REV): ファイルサイズ が指定可能。
       _REV がつくと逆順になります。
 4. ajaxview   … 単語を書くと項目クリックでその場に中身を読み込む (default: 読み込まない)
 5. natural    … 単語を書くと、ファイル名・タイトルを数値として比べる
       (default: 文字として比べる)。`sort`が`FNAME`/`TITLE`系のときだけ効きます
       （`MTIME`/`SIZE`はもともと数値なので指定しても変わりません）
 6. exclude    … `exclude=名前` の形でのみ指定できます (default: 除外しない)
       folderから見た相対パスで照合します。"*"や"?"を含めばワイルドカード、
       含まなければ部分一致です。複数指定するときは ";" で区切ります
       （";" そのものを含めたい場合は "\\;"）
 7. format_md  … `format_md=値` の形でのみ指定できます。**Markdown（.md）の
       ページ**に効く見せかた。FILE: ファイル名 / TITLE: タイトル / BOTH: 両方
       (default: 設定 `markdown.listname` から決まる。既定は TITLE)
 8. format_pk  … `format_pk=値` の形でのみ指定できます。**PukiWiki記法
       （.txt）のページ**に効く見せかた。値の候補は format_md と同じ
       (default: 設定 `pukiwiki.listname` から決まる。既定は FILE)

PukiWiki記法はファイル名を基準に書く歴史的な流儀、Markdownは見出し
（タイトル）を基準に書く流儀があり、一覧の見せかたも記法ごとに既定が
違います（Wiki設計者の指示、2026-09-18）。1つの `#ls()` の中にMarkdownと
PukiWiki記法のページが混ざっていても、それぞれの記法の既定・指定に従って
別々に見せかたが決まります。

`folder`は常に1番目で、これは省略もできます（`#ls(, recursive)`のように
空けて後ろだけ書く）。`recursive`/`sort`/`ajaxview`/`natural`は
folderより後ろなら書きたいものだけ好きな順で書けます。`exclude`・
`format_md`・`format_pk`は`名前=値`の形でしか書けません（位置には
出てきません）。

フォルダの入口ページ（index）は、一覧の項目としては並びません。代わりに
そのフォルダの名前が入口ページへのリンクになります（フォルダの見せかたは、
入口ページの記法に対応する`format_md`/`format_pk`で決まります）。

階層表示（recursive）のフォルダは <details> で畳めます。ここはJavaScript不要です。
"""

""" 技術資料
ajaxview を書いたときだけ plugin/ls.js が働き、クリックされた項目の中身を
`/.plugin/ls?page=<ページパス>` から読み込み、ajax request は `_action()` が対応します。

## 一覧に出るのは公開されたページ

名前も見出しも日時も大きさも、すべて**DB**（pageinfo/wikiall.db）から採ります。
DB の 平文データ の一覧を取得するため、平文データ自体も db から取得します。
wiki ファイル自体はアクセスしません。
見出し も 表示中のページと
食い違い、MTIME もファイルの更新時刻（＝作業中の書き換え）を指してしまいます。

そのため**フォルダも subpath から組み立てます**。「フォルダ」とは、公開された
ページを下に持つ階層のことで、ページを1枚も持たない空のフォルダは出てきません
（もともと畳んでも何も出てこないので、見た目は変わりません）。

folder には "link": True を宣言している。これにより、folder に書いた値が
リンク元データベースに記録される（wikilib.links.plugin_arg_links）。
宣言するだけでよく、_convert側で何かする必要はない。

**その代わり、folder の解きかたも本体に合わせる義務が生じる**
（`_resolve_folder` は `paths.full_pagepath` を呼ぶだけにしてある）。
記録と改名への追従は `wikilib.links` / `wikilib.pluginlinks` が
`resolve_href`（＝`full_pagepath`）で解釈するので、プラグイン側が独自に
解くと、記録された先と実際に一覧する先が食い違う。

## num_orderによる自由順序化（2026-08-23）

`folder`だけ`num_order: 1`で位置を固定し、`recursive`/`sort`/`format`/
`ajaxview`は`num_order`を宣言しない自由順序にした（詳しくは
`Tech/PluginGuide`の「引数を自由な順番で書けるようにする」の節）。

`recursive`/`ajaxview`は`"flag": True`（`candidate: [自分の名前],
type: "bool"`の糖衣構文）にした。本家PukiWikiの多くのプラグインに
倣い、単語を書くだけで有効になる。

`sort`/`format`は両方とも`candidate`に`"TITLE"`を持つため、単独で
`TITLE`と書いた場合は**宣言順が先の`sort`が受け取る**（自由順序の
仕様どおり、複数のオプションが同じトークンにマッチしうる場合は
宣言順で先勝ち）。`format`だけを`TITLE`にしたい場合は`format=TITLE`と
名前で指定する必要がある。`sort`/`format`の値検証は、以前は`_convert`内で
手動チェックしていたが、`candidate`宣言に移した（フレームワークの
エラーメッセージも候補一覧つきで、以前の手動メッセージと遜色ない）。

## `recursive`でフォルダを含めると名前順が崩れていた不具合（2026-09-03修正）

Wiki設計者の報告:「lsプラグインで名前ソートができない。recursiveオプションを
付けている」。原因は`_render_tree`が**ページを`sort`/`reverse`どおりに
並べたあと、フォルダを別に（常に名前の昇順だけで）並べて後ろへ連結**
していたこと。`recursive`が無い、またはそのフォルダに下位フォルダが
無いページ一覧では表に出ない（フォルダが1件も無ければ「別々に並べて
連結」しても結果は同じため）。フォルダを含む一覧で初めて、「ページ全部→
フォルダ全部」という順序のズレが見えていた（例:
ページ`Apple`/`Zebra`とフォルダ`Middle`があると、本来`Apple, Middle,
Zebra`の順になるはずが`Apple, Zebra, Middle`になっていた。`FNAME_REV`
では逆にフォルダだけ昇順のまま取り残されるズレも同時にあった）。

`_render_tree`を、ページ・フォルダを`(並び替えの値, HTML片)`のリストへ
まとめてから**最後に1回だけ`sort`する**形に直した。フォルダの並び替えの
値は、`_folder_sort_item()`で**入口ページ（index）があればそのページと
同じ値**（`name`/`title`/`updated`/`size`）を代用し、無ければ名前だけで
代用する（更新日時・大きさで比べる場面では「不明」の扱いになる。技術的な
妥協点だが、フォルダ自体に単一の更新日時・大きさという概念が元々無いため
やむを得ない）。`format=TITLE`表示中でも、フォルダの並び替えの値は表示に
使うタイトルとは独立に`sort`の基準（既定は`FNAME`）で決まる点に注意
（`Syntax/Plugin/ls.md`の表示例参照）。

## `ajaxview`がフォルダの入口（index）に効いていなかった不具合（2026-09-03修正）

Wiki設計者の報告:「lsでajaxviewがフォルダのindexだと反応しない」。原因は、
`_render_tree`のフォルダの見出し（`head`）を組み立てる箇所が、
`_render_page`のように`ajaxview`時の「その場で開く」ボタン
（`.ls-open`）と受け皿（`.ls-view`）を付けておらず、常に素の`<a>`
リンクだけを返していたこと。フォルダの入口ページが表示上「1件のページ」
として並ぶ場合（下に他の中身が無く、`<details>`に畳まれない場合）でも、
クリックするとページ遷移するだけで、その場に開く動きをしなかった。

**入口ページだけで中身が無いフォルダ**（ページと同じ見た目で1件の`<li>`
として並ぶ場合）に限って直した。`_label()`/`_render_page()`に
`display_name`（省略時は`page.name`をそのまま使う）を足し、フォルダの
入口ページを描くときはフォルダ名を`display_name`として渡すことで、
`_render_page(index_page, fmt, ajaxview, display_name=folder["name"])`を
そのまま使い回せるようにした（表示名だけがページ名からフォルダ名に
差し替わり、他の挙動は普通のページの`ajaxview`と完全に同じになる）。

**中身がある（`<details>`に畳まれる）フォルダの`<summary>`側は、当初
対象外にしていた。** `<summary>`は元々クリックで`<details>`の開閉を
担っている要素で、その中に`.ls-open`ボタンを重ねて置くと、ボタンを
押したときに「その場でindexページを開く」動きと「フォルダ自体の開閉」が
同時に起きてしまう（`<summary>`内の要素をクリックしても、既定ではその
祖先の`<details>`のトグルが働くため）。

Wiki設計者に確認したところ、実際に反応しなかったのは**この`<summary>`側**
だったため、続けて対応した（下記）。

## `<summary>`側のajaxview対応（上記と同日、追加対応）

`_render_tree`のフォルダ描画で、`inner`（中身）がある場合も
`ajaxview`時は`index_page`があれば`.ls-open`ボタン・`.ls-view`を
`<summary>`の中と直後に足すようにした（`<li class="ls-folder
ls-openable">`。目印クラス`ls-openable`は`_render_page`の`ls-page
ls-openable`と共通化してある）。`.ls-view`は`<summary>`の**外**
（`<details>`の直下、`<summary>`の次）に置く（`<summary>`の中身は
見出しの文言に留めたいのと、`<summary>`の中に`<div>`のようなブロック
要素を入れるより、直後に並べるほうが素直なため）。

`plugin/ls.js`側は2点直した。

1. `.ls-open`クリック時に**`event.preventDefault()`を必ず呼ぶ**（`<li
   class="ls-page">`側では防ぐべき既定動作が元々無いので害はなく、
   `<summary>`側でだけ効いて`<details>`のトグルを止める）
2. 受け皿を探す起点を`.closest(".ls-page")`から**`.closest(".ls-openable")`**
   に変更（`ls-page`・`ls-folder`のどちらのulliにも共通で乗っている
   目印クラスなので、片方専用の判定にならずに済む）

headless Chromeで、ボタンを押しても`<details>`の開閉状態
（`.open`プロパティ）が変わらないこと・`.ls-view`は正しく開いて中身が
読み込まれること・**`<summary>`自体をクリックした場合は従来どおり
`<details>`が開閉すること**（ボタン以外の場所をクリックしたときの
既定動作は壊れていないこと）を確認した。

## 自然順ソート（`natural`）の追加（2026-09-04）

`Tech/ChangeLog/plugin/index.md`の「今後の予定」に置かれていた案（Wiki設計者の
提供のkey案。正の整数だけを前提にできるなら、と付記されていた）の考えかたを
採用した:

#code(python){{
key=lambda s:[int(c) if c.isdecimal() else c for c in re.split('([0-9]+)',s)]
}}

**`sort`の値（`NATURAL`/`NATURAL_REV`）としてではなく、`recursive`/
`ajaxview`と同じ独立の`flag`引数にした。** 最初は`SORTS`に`NATURAL`/
`NATURAL_REV`という項目を足す実装で作ったが、Wiki設計者から「naturalは
これまでとは独立のオプション。ファイル名やタイトルに適用させるため」と
指摘を受け、作り直した。`sort=FNAME`（ファイル名）と`sort=TITLE`
（タイトル）のどちらにも「数字を数値として比べるか」を掛け合わせたい、
という要求で、`sort`の候補を1つ増やす形（ファイル名専用の`NATURAL`）
では`TITLE`側に適用できない。`natural`を`sort`とは別軸の真偽値にする
ことで、`#ls(sort=TITLE, natural)`のように両方を独立に選べるようにした。

`_sort_key(item, key, natural=False)`が、`key`が`"name"`/`"title"`
（文字列を比べる場面）のときだけ、比較の値を通常の`(小文字, 元の文字列)`
から`(_natural_key(...), 元の文字列)`へ差し替える。`updated`/`size`
（`MTIME`/`SIZE`）はもともと数値そのものなので、`natural`を付けても
比較の仕方は変わらない（エラーにもしない。効果が無いだけで、指定した
こと自体を咎める理由が無いと判断した）。

`[0-9]+`ではなく`\\d+`にした。Python 3の`re`は既定（`re.ASCII`を付けない）
だと`\\d`がUnicodeのdecimal digit全般（`str.isdecimal()`がTrueになる文字、
全角数字を含む）にマッチするため、`[0-9]+`から`\\d+`に変えるだけで全角にも
対応できる（`int()`自身も全角数字の文字列をそのまま整数に変換できる。
`int("１０")`は`10`になる）。動作は`_venv`のPythonで実測して確認済み。

`re.split(r"(\\d+)", s)`は「区切られなかった文字列部分」と「数字の
かたまり（キャプチャされた部分）」が**必ず交互に**並ぶ（先頭は常に文字列
側。数字で始まる文字列でも、先頭に空文字列が入るだけで交互の並びは
崩れない）。そのため、2つの文字列の`_natural_key()`どうしをリストとして
比べるとき、同じ位置（index）どうしは相手の文字列の中身に関わらず必ず
同じ型（偶数番目はstr、奇数番目はint）になる。Pythonの`int`と`str`は
直接比較できず`TypeError`になるが、この性質のおかげで型が食い違う位置
まで比較が進むことはなく、安全にリストどうしの大小比較ができる（比較は
先頭から順に見て、途中の要素が一致すれば次の要素へ進み、要素数が違う
場合は短い方が「先に尽きる」ため小さい扱いになる、という通常のPythonの
リスト比較のルールのまま）。

文字列部分は`FNAME`同様に大文字小文字を無視して比べる（`.lower()`）。
ほかの`SORTS`のキーと同じく、`_sort_key()`側で`(自然順の鍵, 元の文字列)`
のタプルにしてある（自然順の鍵が完全に同じになる場合の並びを、元の
文字列で安定させるため）。

## フォルダの判定をOSのフォルダ／ファイルに頼らない（2026-09-05）

Wiki設計者の報告:「`=freshtest/講義`で`#ls`を使っても`第07回/`を得られません。
`講義/第07回`はページとしてアクセス可能です。」

原因は、`recursive`を付けない`#ls()`が、indexページを持つサブフォルダを
一覧から一切出さない仕様になっていたこと（`Syntax/Plugin/ls.md`に
「recursiveを書かないときは、サブフォルダ自体が一覧に出ません」と
明記されていた、意図した仕様ではあった）。ただし、フォルダの中に
子ページが1つも無く**入口（index）だけを持つ**場合、非recursiveでは
一覧が空になってしまい、実用上ページとして機能しているものが見えなく
なる。

Wiki設計者の指摘: **「OSのフォルダとwikiのフォルダは意味が違う。wikiの世界
では、フォルダでもindexがあればページとみなす必要がある。ページかどうか
の評価はwikiSystemが用意する関数で判定し、プラグイン自身がフォルダ名
だけでファイルかどうかを判断しないようにする。」** それまでの`_scan`は
DBのsubpathを`/`で自分で分割し、「直下で終わる＝ページ」「まだ`/`が
続く＝フォルダ」というOSのファイル/ディレクトリの発想で判定していた。
これがそもそもの設計ミスだった。

Wiki設計者の指示によりwikiSystemへ、判定そのものを引き受ける関数の新設を
依頼した（コミット`5df525c`、Rev.193）:

    wikilib.pagedb.page_children(wiki_dir, prefix="", entries=None)
    → [{"name": 直下の名前, "page": ページ辞書 or None,
        "has_more": その名前の下にpage以外の公開ページがまだあるか}, ...]

`page`にはindexページを持つフォルダも「実体」として入る（`page_entries`
の1行＋`pagepath`）。`_scan`はこれをそのまま使い、`/`分割による独自の
フォルダ／ページ判定を一切しなくなった。`has_more`が`True`のものだけ
`folders`（`<details>`に畳む余地があるもの）へ、`False`のものは
（`page`があれば）`pages`へ、という振り分けだけになった。

**`index_page`を`folders`側に持たせ、`recursiveかどうかに関わらず**
常に分かるようにした**のが今回の要点**（旧`_scan`は`recursive`のときだけ
`child`を作り、`_render_tree`が`child["pages"]`の中から`name == "index"`を
探して初めてフォルダの入口を知る作りだったため、非recursiveでは
`child`自体が`None`で入口の有無すら分からなかった）。`_render_tree`は
`folder["index_page"]`を直接読むだけでよくなり、`child is None`
（非recursive）でも入口さえあればフォルダを1件のページとして出せる。

`_drop_self`（自分自身を一覧から外す処理）も、`index_page`が`pages`とは
別の場所に移ったため、`folders`側の`index_page`も個別に見て、自分自身と
一致すれば外すよう直した（そうしないと、フォルダの入口ページが自分の
親フォルダの`#ls`結果に、自分自身へのリンクとして残ってしまう）。

`walk`/`glob`に相当するwiki世界用の関数（Wiki設計者が言及した3つのうちの
残り2つ）は、`ls.py`の直し自体には不要だったため、今回は依頼していない
（`_sys`側でOSとwikiの概念の違いを`Tech`にまとめる別件を、利用者が
wikiSystemへ依頼中とのこと）。

## 入口ページ（index）を一覧の項目にしない（2026-09-18）

Wiki設計者の指示:「lsプラグインでは一覧から index を対象外にすること。」

`#ls(/Docs)` のように**自分以外のフォルダ**を一覧すると、そのフォルダの
入口ページが `index` という名前の項目として並んでいた（リンク先は
`/Docs`、添え書きは入口ページのタイトル）。一覧したいのは「`/Docs` の
中身」であって `/Docs` 自身ではないので、`_scan` が `INDEX_NAME` の item を
`pages` に入れないようにした。

`_drop_self`（いま読んでいるページ自身を外す処理）とは役割が違うので
両方残してある。`_drop_self` は「`/Docs/Intro` を開いたまま `#ls(/Docs)` と
書いた」ような、index ではないページが自分自身になる場合に効く。
以前は「フォルダの入口ページに `#ls()` を置く」という一番多い使いかたが
`_drop_self` に頼って index を隠していたが、いまは `_scan` の段階で落ちる
（フォルダの入口に置いたかどうかに関わらず、常に並ばなくなった）。

`_render_tree` が `child["pages"]` から `p.name != "index"` を外していた
処理は、`_scan` が落とすようになったぶん不要になったので削除した
（同じ判断が2か所にあると、片方だけ直したときに食い違う）。

## `exclude`（除外）を追加（2026-09-18）

Wiki設計者の指示:「exclude オプションを作り、指定されたファイルは除外する。
複数個を設定する場合は ; で区切る。」

`recent` の `exclude`（`wikilib.search.name_matches`・`split_filters`）と
同じ規則を採用した。書きかた・照合の細則を2つそろえて覚えなくて済むように
するためで、`recent` 側の実装をそのまま使い回している。

**`recent` と1点だけ違う: 照合の対象をwikiのsubpath全体ではなく、
`folder` からの相対パスにした。** `recent` はWiki全体を対象にした一覧
（`exclude` はどこにあるページかを問わず除外したい）だが、`ls` は
「指定したフォルダの中」を見せるプラグインなので、subpath全体で照合すると
`#ls(/Tech/ChangeLog, exclude=ChangeLog)` のように**対象フォルダ自身の
名前を含むだけで一覧が丸ごと空になる**事故が起きる（`ChangeLog/2026-08-11`
のようなsubpathの多くが`ChangeLog`という文字列を部分一致で含むため）。
`_relative_to()` で `folder` を基準に取り除いてから照合することで、
`exclude=plugin` は直下の `plugin` フォルダだけを、`recursive` 時に
深い階層を狙いたければ `exclude=ChangeLog/plugin` のように書けば済む
ようにした。

**フォルダがexclude対象なら、中身ごと走査しない。** `_scan` の再帰呼び出し
に入る前に判定しているので、除外したフォルダの下を無駄に辿らない
（`recursive` 指定時、除外したフォルダが大きくても走査コストが増えない）。

**`kw_only: True` を宣言し、`exclude=...` の名前付きでしか書けないように
した。** `folder` に続く `recursive`/`sort`/`format`/`ajaxview`/`natural`
は自由順序（`candidate` を書かない項目は「何にでもマッチする」）なので、
単純に `{"name": "exclude", "default": None}` を足すと `#ls(Tech, BADSORT)`
のような**打ち間違いまで exclude に黙って吸われ、意図したエラー検出が
壊れる**。`kw_only` は wikiSystem 本体（`_sys/wikilib/plugins.py`）への
要望として `request_65c6c6.md` にまとめ、Wiki設計者の承認を経て実装を
依頼した（コミット `4bfd219`。依頼の経緯は
[更新履歴](/Tech/ChangeLog/plugin/2026-09-18)参照）。実装は依頼した設計
どおりで、`#ls(Tech, BADSORT)`／`#ls(Tech, exclude か何かを位置で書こうと
した場合)` のどちらも引き続きエラーになることを確認済み。

`link: True` は付けていない。`exclude` の値はページそのものへの参照では
なく、`name_matches` による部分一致/ワイルドカードの指定（`recent` の
`exclude` と同じ）なので、リンク元DBに記録する対象ではないと判断した。

## フォルダの指しかたが本文のリンクと食い違っていた（2026-09-18修正）

Wiki設計者の指摘:「`ls` plugin でページ名に `foo` としたら `/foo` が参照
されるのか？ `./foo` が参照されるのか？ リンクの定義を踏まえると `/foo` を
参照すべきだが。」

そのとおりだった。`_resolve_folder`が`os.path.normpath`で独自に解いており、
`/`始まり以外をすべて相対として扱っていたため、`foo`/`./foo`/`../foo`の
**3通りとも**`paths.full_pagepath`（本文のリンクの決まり）と食い違っていた。
`paths.full_pagepath`に委ねるだけの形に直した（`_resolve_folder`参照）。

実害は2つあった。

1. **メニューページで指す先が揺れていた。** `mainmenu`は表示中のページの
   contextで描かれる（`themes.render_menu`）ため、旧実装では起点が
   表示中のページになる。`1ev-c`の`mainmenu.txt`にある`#ls(講義/)`が、
   `/index`では`/講義`（正常）、`/演習/第01回`では`/演習/第01回/講義`、
   `/講義/第01回`では`/講義/講義`（どちらもエラー）になっていた
2. **記録と表示が食い違っていた。** `"link": True`のため、リンク元DBへの
   記録もリネーム追従も`full_pagepath`で解釈される（上の節を参照）

既存の`#ls(...)`呼び出しは`wikidata`配下の全Wikiを新旧両実装で突き合わせた。
35件中26件は不変、9件は指す先が変わるが**すべて旧実装で「存在しない
フォルダ」＝エラー表示になっていたもの**（`Syntax/Plugin/ls`の利用例など）で、
動いていたものが壊れる呼び出しは無かった。

独自実装を捨てたことで`_is_folder`（相対の起点を「ページ自身か親か」で
決める判定。2026-09-17に足したばかりだった）・`_own_folder`・realpathによる
Wiki外チェック・`import os`がまとめて不要になった。

## `format`を`format_md`/`format_pk`へ分割（2026-09-18）

Wiki設計者の指示:「pukiwiki はファイル名を基準に、markdown はタイトルを
基準にするのがファイルの記述方法の背景にあるので、双方で統一のルールには
できません。そこでこの設定を分離し、それぞれの記述方法で表示するものを
変える設定を導入します。」

きっかけは編集画面のページ一覧（サイドバー）の調査だった。`RightBar.txt`
（PukiWiki記法）が一覧に見えないという報告を追うと、一覧はファイル名では
なく**タイトル優先**で表示する作り（`editor.js`の`titleOnly`）になっており、
PukiWiki記法の`RightBar`は本文の見出し「演習やポイント」として表示され、
見た目上「RightBarという名前が無い」ように見えていた——バグではなく仕様
だった。ただしこれを機に、Wiki設計者から「一覧の取得方法」自体の見直しの
依頼を受けた。

新設の設定`markdown.listname`/`pukiwiki.listname`（`wikiconfig.listname_for`。
既定はmarkdown=title、pukiwiki=fname）を、`ls`の見せかたの既定にも使う。
1つの`#ls()`の中にMarkdownとPukiWiki記法のページが混ざっていても、
ページごとの記法で見せかたが変わる必要があるため、**単一の`format`では
表現できない**——そこで`format`を廃止し、`format_md`（Markdown向け）・
`format_pk`（PukiWiki記法向け）の2本に分けた。値の候補（FILE/TITLE/BOTH）は
変えていない。

### 後方互換は取らなかった

`format`をそのまま残し「明示されたときだけ両方の記法へ一律適用する」形も
検討候補として提示したが、Wiki設計者は「formatを廃止し既存ページを書き
換える」を選んだ。`Tech/ChangeLog`配下・`Syntax/Plugin/ls`など`format=`を
使っていた呼び出し（15箇所前後）は、実際に稼働している`#ls(...)`呼び出し
（各`index.md`など）だけを`format_md=`へ書き換えた。ChangeLogの日付記事に
`` `format=TITLE` `` と*歴史の記述として*出てくる箇所（当時それが正しい
書きかただったことの記録）は書き換えていない——過去の記録を今の仕様に
合わせて書き換えると、その日に何が正しかったかが分からなくなるため。

### 実装

- `PageItem`（`wikilib.pagelist`）に`ext`を足した。DB側（`page_entries`の
  `path`列）・平文側（`_file_rows`が`os.path.splitext`で拾ったもの）の
  どちらからも拾えるようにしてある
- `_format_for(item, fmt_md, fmt_pk)`が、`item.ext`から記法
  （`paths.markup_name_for`）を引いて`format_md`/`format_pk`のどちらを
  使うか選ぶ。記法が分からない項目（実体の無い通り道のフォルダ）はFILE扱い
- フォルダの見せかたは、フォルダ自体が記法を持たないため**入口ページ
  （index）の記法**で決める（`_render_tree`の`folder_fmt`）
- `format_md`/`format_pk`は`exclude`と同じ`kw_only: True`。`sort`も
  `TITLE`という値を持てるため、自由順序（位置引数）に混ぜると衝突しうる
  （旧`format`で経験済みの問題。技術資料「`sort`/`format`は両方とも
  candidateに"TITLE"を持つため…」参照）。新設の2つは常に`名前=値`で
  書かせることで、その曖昧さそのものを無くした

編集画面のページ一覧（サイドバー）も同じ設定を使うようにした
（`editor._apply_listnames`・`treeview.js`の`listname`）。あちらは
ファイル名・タイトルのどちらか一方しか出せない幅の狭い一覧なので、
`ls`の`BOTH`に相当する選択肢は無い。
"""
import re
from html import escape

from wikilib import pagelist
from wikilib.auth import PAGE_NONE
from wikilib.pagedb import published_ref
from wikilib.paths import (
    INDEX_NAME, PLUGIN_URLPATH, full_pagepath, is_valid_pagepath,
    farm_plugin_dir, markup_name_for, resolve_page_ref,
)
from wikilib.plugins import FREE_TEXT, PluginArgumentError
from wikilib.search import name_matches, split_filters
from wikilib.wikiconfig import listname_for

SORT_CANDIDATES = ["FNAME", "FNAME_REV", "MTIME", "MTIME_REV", "TITLE", "TITLE_REV", "SIZE", "SIZE_REV"]
FORMAT_CANDIDATES = ["BOTH", "FILE", "TITLE"]

PLUGIN_INFO = {
    "help": "#ls(folder,recursive,sort,ajaxview,natural,exclude,format_md,format_pk)",
    "args": [
        {"name": "folder", "num_order": 1, "candidate": [FREE_TEXT], "default": None, "link": True},
        {"name": "recursive", "flag": True, "default": False, "label": "再帰"},
        {"name": "sort", "candidate": SORT_CANDIDATES, "default": "FNAME"},
        {"name": "ajaxview", "flag": True, "default": False, "label": "その場表示"},
        {"name": "natural", "flag": True, "default": False, "label": "自然順"},
        {"name": "exclude", "kw_only": True, "default": None, "label": "除外"},
        {"name": "format_md", "kw_only": True, "candidate": FORMAT_CANDIDATES, "default": None,
         "label": "見せかた（Markdown）"},
        {"name": "format_pk", "kw_only": True, "candidate": FORMAT_CANDIDATES, "default": None,
         "label": "見せかた（PukiWiki）"},
    ],
}

# 並び順。値は (並べ替えの鍵, 逆順にするか)。
# "_REV" が付かないほうを昇順（名前はA→Z、日時は古い順、大きさは小さい順）に揃えている。
# MTIME が指すのはDBの updated（＝公開された日時）で、書きかけのファイルを
# 触った時刻ではない。書きかたとしての名前は変えていない。
SORTS = {
    "FNAME": ("name", False), "FNAME_REV": ("name", True),
    "MTIME": ("updated", False), "MTIME_REV": ("updated", True),
    "TITLE": ("title", False), "TITLE_REV": ("title", True),
    "SIZE": ("size", False), "SIZE_REV": ("size", True),
}

# 自然順ソート用。連続する数字のかたまりで区切り、数字部分だけ int にする
# （"page2" が "page10" より前に来るようにする）。\d は Unicode の decimal
# digit 全般（全角数字を含む）にマッチするので、全角の番号も同様に扱える。
_NATURAL_SPLIT = re.compile(r"(\d+)")


def _natural_key(name):
    """"page10" > "page2" になるよう、数字のかたまりをintとして比べる鍵を作る。

    re.split の結果は「区切られなかった部分（文字列）」と「数字のかたまり
    （キャプチャされた部分）」が必ず交互に並ぶ（先頭は文字列側、無ければ
    空文字列）。そのため同じ位置どうしを比べるとき、型（strかintか）は
    比べる相手の文字列の中身に関わらず常に揃う（＝strとintを直接比べて
    落ちることが無い）。文字列側は大小文字を無視して比べる。"""
    return [int(part) if part.isdecimal() else part.lower() for part in _NATURAL_SPLIT.split(name)]


def _resolve_folder(context, raw):
    """指定されたフォルダを wiki/ からのパスに直す。ページ名にできない指定なら None。

    **解くのは `paths.full_pagepath`（本文のリンクと同じ関数）に任せる。**
    `Tech` はとなりではなくルートからの絶対、`./Tech` が自分の下、
    `../Tech` が1つ上、という本家PukiWiki（get_fullname）ゆずりの決まりが
    そのまま効く。書き手が `[[Tech]]` と `#ls(Tech)` で別の場所を
    思い浮かべずに済むのが第一の理由だが、folder は `"link": True` を
    宣言している以上、**合わせないと実害が出る**：リンク元データベースへの
    記録もページ改名への追従も `full_pagepath` で解釈されるため、記録先と
    一覧する先が食い違ってしまう（技術資料の冒頭参照）。

    2026-09-18まではここで `os.path.normpath` を使って独自に解いており、
    `/` 始まり以外をすべて「今のページのフォルダから見た相対」として
    扱っていた。そのため裸の `#ls(Tech)` が `/Tech` ではなく
    `いまのページ/Tech` を探し（たいてい「フォルダが見つかりません」）、
    `../` は1つ余分に上がっていた。Wiki設計者の指摘で判明し、本体に
    委ねる形へ直した。

    省略（`raw` が None）・`.` は `full_pagepath` が base をそのまま返すので
    「自分の下」になる。そのページがフォルダの入口（index）ならそのフォルダ
    自身、単独ページなら「自分と同じ名前のフォルダ」で、たいてい存在せず
    一覧は空になる（仕様どおり、これはエラーにしない）。

    `..` がWikiの外へ出る心配は `full_pagepath` がルートで止めるため無い
    （独自実装で要っていた realpath による確認も、それごと不要になった）。
    残る不正は `=`（Wiki指定）・`.`（システム資材）で始まる予約名だけなので、
    そこだけ `is_valid_pagepath` で弾く。"""
    folder = full_pagepath((context.page or "").strip("/"), (raw or "").strip())
    return folder if is_valid_pagepath(folder) else None


def _relative_to(subpath, top_folder):
    """subpath を、一覧の対象として指定された folder（top_folder）から見た
    相対パスにする（先頭の "/" は付けない）。exclude の照合はこの相対パスに
    対して行う（wikiのsubpathそのままだと、深い階層のフォルダを
    `exclude=plugin` のような短い名前で書けなくなるため）。"""
    if not top_folder:
        return subpath
    prefix = top_folder + "/"
    return subpath[len(prefix):] if subpath.startswith(prefix) else subpath


def _is_excluded(rel, excludes):
    return any(name_matches(rel, pattern) for pattern in excludes)


def _scan(context, folder, recursive, excludes=(), top_folder=None):
    """フォルダの中身を {pages, folders} の木にして返す。フォルダが無ければ None。

    **一覧は `wikilib.pagelist` から取る**（2026-09-17）。以前はDBを自分で引いて
    （`page_entries`＋`page_children`）階層を組み立てていたが、その走査は
    `pagelist.scandir` が受け持つようになった。ここに残るのは**見せかたの都合**
    ——ページとフォルダに振り分け、`<details>` に畳む単位を決めるところだけである。

    `scandir` が返す `PageItem` は、

        exists          そこにページの実体があるか（通り道のフォルダは偽）
        has_children    **その人に見える**ページが下にあるか

    を持つ。フォルダの入口（`Tech/index`）はページ `Tech` として1件にまとまって
    返るので、`folders` 側に `index_page` として持たせる（`<details>` に畳むか
    どうかは、まだこの時点では決まっていないため、`pages` へは混ぜない）。

    **閲覧の権限はこの中には出てこない。** `pagelist` が既定で「読めるものだけ」を
    返し、下が全部隠れたフォルダも落としてくれる（[ページの一覧を作る](/Tech/PageList)）。

    見えるページを1枚も持たない階層は出てこない。その場合そもそも「フォルダが
    無い」ことになるので、`#ls(存在しないフォルダ)` は今までどおりエラーになる。

    **`exclude`（2026-09-18追加）は最初の呼び出しの `folder` を基準にする。**
    `top_folder` を省略した最初の呼び出しでそれをそのまま基準に固定し、
    `recursive` による再帰呼び出しにも引き継ぐ（引数を増やさず基準だけ
    渡したいので、既定値 `None` を「まだ決めていない」の印に使っている。
    `folder` がWikiの直下（空文字列）でも `top_folder is None` との比較なら
    正しく区別できる）。**フォルダがexclude対象なら、中身ごと走査しない**
    （除外したフォルダの下を辿っても無駄なため。`recursive` 指定時、深い
    階層のフォルダを狙って `exclude=plugin` のように書ける）。"""
    if top_folder is None:
        top_folder = folder
    items = pagelist.scandir(context.wiki_dir, under=folder, privilege=context.privilege)
    if folder and not items:
        return None

    prefix = folder + "/" if folder else ""
    pages, folders = [], []
    for item in items:
        if item.name == INDEX_NAME:
            # フォルダの入口ページは項目として並べない（Wiki設計者の指示、
            # 2026-09-18）。指している先はこのフォルダ自身で、「中身」では
            # ないため。入口の見出し・リンクは、親側が `index_page` として
            # フォルダ名の行に出す（`_render_tree`）。
            continue
        if not item.has_children:
            # これ以上下に見えるページが無い。ページそのもの（フォルダの
            # 体裁でindexだけを持つ場合を含む）なら pages へ
            if item.exists:
                if excludes and _is_excluded(_relative_to(item.subpath, top_folder), excludes):
                    continue
                pages.append(item)
            continue
        folder_subpath = prefix + item.name
        if excludes and _is_excluded(_relative_to(folder_subpath, top_folder), excludes):
            continue
        folders.append({
            "name": item.name,
            "subpath": folder_subpath,
            "index_page": item if item.exists else None,
            "child": _scan(context, folder_subpath, recursive, excludes, top_folder) if recursive else None,
        })
    return {"pages": pages, "folders": folders}


def _drop_self(node, self_subpath):
    """一覧から、いま読んでいるページ自身を取り除く。

    フォルダの入口ページに #ls() を置くと、そのページ自身が一覧に入ってしまう。
    「ここから下にあるページ」を見せたいので、自分は出さない。フォルダの
    `index_page`が自分自身（親フォルダの入口として#ls()を置いたページ）を
    指している場合も、同様に外す（`_scan`が`index_page`を`pages`とは別に
    持つようになったため、こちらも個別に見る必要がある）。"""
    if not self_subpath:
        return node
    return {
        "pages": [p for p in node["pages"] if p.subpath != self_subpath],
        "folders": [
            {**f,
             "index_page": None if f["index_page"] and f["index_page"].subpath == self_subpath
                           else f["index_page"],
             "child": _drop_self(f["child"], self_subpath) if f["child"] else None}
            for f in node["folders"]
        ],
    }


def _sort_key(item, key, natural=False):
    """並び替えの比較値。`item` は `PageItem`、またはフォルダの代わりに
    渡す同じ形の `PageItem`（`_folder_sort_item` 参照）。

    `natural`は`sort`（`key`）とは独立の指定（Wiki設計者の指示、2026-09-04：
    「naturalはこれまでとは独立のオプション。ファイル名やタイトルに適用
    させるため」）。`key`が`name`/`title`（文字列を比べる場面）のときだけ、
    比較の値を`_natural_key()`（数字のかたまりをintとして比べる）に
    差し替える。`updated`/`size`はもともと数値そのものなので対象外
    （`natural`を付けても指定前と同じ並びになる。エラーにはしない）。"""
    if key == "name":
        return (_natural_key(item.name), item.name) if natural else (item.name.lower(), item.name)
    if key == "title":
        # タイトルが無ければファイル名で代用する（並びが飛ばないように）
        t = item.title or item.name
        return (_natural_key(t), t) if natural else (t.lower(), t)
    return (getattr(item, key), item.name.lower())


def _folder_sort_item(folder_name, index_page):
    """フォルダを、ページと同じ形（`PageItem`）で並び替えに使えるようにする。

    入口ページ（index）があれば**そのページと同じ値**（更新日時・大きさ・
    タイトル）で比べる。無ければ名前だけで代用する（更新日時・大きさは
    比べようが無いので、その並び順では実質「不明」＝先頭寄りの扱いになる）。"""
    if index_page is not None:
        return pagelist.PageItem(name=folder_name, pagepath=index_page.pagepath,
                                 subpath=index_page.subpath, title=index_page.title,
                                 updated=index_page.updated, size=index_page.size)
    return pagelist.PageItem(name=folder_name, pagepath="", subpath="", updated="", size=0)


def _format_for(item, fmt_md, fmt_pk):
    """そのページの記法（拡張子）から、`format_md`/`format_pk`のどちらを
    使うか選ぶ（Wiki設計者の指示、2026-09-18。「pukiwiki はファイル名を
    基準に、markdown はタイトルを基準にするのがファイルの記述方法の背景に
    あるので、双方で統一のルールにはできない」）。

    記法が分からない項目（実体の無い通り道のフォルダなど。`item.ext`が
    無い）は FILE 扱いにする——出せる名前がファイル名しか無いため。"""
    markup = markup_name_for(item.ext) if item and item.ext else None
    if markup == "markdown":
        return fmt_md
    if markup == "pukiwiki":
        return fmt_pk
    return "FILE"


def _default_format(config, markup):
    """`format_md`/`format_pk`を省略したときの既定値。

    設定（`markdown.listname`/`pukiwiki.listname`。`wikiconfig.listname_for`）を
    ここで`FORMAT_CANDIDATES`の語彙（FILE/TITLE）に読み替える。"""
    return "TITLE" if listname_for(config, markup) == "title" else "FILE"


def _label(page, fmt, display_name=None):
    """一覧に出す文字。format（`_format_for`が選んだもの）の指定で変わる。

    `display_name`を渡すと、ページの名前（`page.name`）の代わりにそちらを
    使う。フォルダの入口ページを「ページ名（"index"）」ではなく
    「フォルダ名」で見せるときに使う（`_render_tree`参照）。"""
    name = page.name if display_name is None else display_name
    title = page.title
    if fmt == "FILE":
        return escape(name), ""
    if fmt == "TITLE":
        return escape(title or name), ""
    # BOTH。タイトルが無いページは名前だけ出す
    return escape(name), escape(title) if title else ""


def _render_page(page, fmt, ajaxview=False, display_name=None):
    main, sub = _label(page, fmt, display_name)
    extra = f'<span class="ls-title">{sub}</span>' if sub else ""
    if not ajaxview:
        return f'<li class="ls-page"><a href="/{escape(page.pagepath)}">{main}</a>{extra}</li>'
    # 開くためのボタンと、読み込んだ中身を入れる場所を添える。
    # ページ名は今までどおりリンクのままにして、そのページへ移る道も残す。
    path = escape(page.pagepath)
    return (
        '<li class="ls-page ls-openable">'
        f'<button type="button" class="ls-open" data-page="{path}" '
        'aria-expanded="false" aria-label="ここに開く">▸</button>'
        f'<a href="/{path}">{main}</a>{extra}'
        '<div class="ls-view" hidden></div>'
        "</li>"
    )


def _render_tree(node, fmt_md, fmt_pk, key, reverse, ajaxview=False, natural=False):
    """フォルダとページを1つのリストにまとめる。フォルダは <details> で畳める。

    ページ・フォルダを分けて並べてから連結するのではなく、**1つの並び順
    （sort/reverse）へ両方まとめてから**出す（`(並び替えの値, HTML片)`を
    集めて最後に1回だけsortする）。以前はページを並べたあとにフォルダを
    別に並べて後ろへ足していたため、フォルダを含む一覧では名前順が保たれて
    いなかった（例: ページ`Apple`/`Zebra`とフォルダ`Middle`があると、
    本来`Apple, Middle, Zebra`の順になるはずが`Apple, Zebra, Middle`に
    なっていた。Wiki設計者の報告により発見）。

    **見せかたは`fmt_md`/`fmt_pk`の2本を受け取り、ページごとに`_format_for`
    で選ぶ**（Wiki設計者の指示、2026-09-18。記法ごとに見せかたの既定が
    違うため、1つの一覧にMarkdownとPukiWiki記法のページが混ざっていても
    それぞれの既定・指定どおりに描ける）。"""
    entries = [(_sort_key(page, key, natural),
                _render_page(page, _format_for(page, fmt_md, fmt_pk), ajaxview))
               for page in node["pages"]]

    for folder in node["folders"]:
        # フォルダの入口（index）は_scanが既に判定済み（技術資料「フォルダの
        # 判定をOSのフォルダ／ファイルに頼らない」参照）。recursiveでなくても
        # （child is None でも）index_pageは分かるようになった。
        index_page = folder["index_page"]
        child = folder["child"]
        if child is not None:
            # indexは `_scan` が落としているので、そのまま描ける（入口ページは
            # folder["index_page"] 側でフォルダ名の行として出る）。
            inner = _render_tree(child, fmt_md, fmt_pk, key, reverse, ajaxview, natural)
        else:
            inner = []
        if not inner and index_page is None:
            continue  # 中身も入口も無いフォルダは出さない

        folder_key = _sort_key(_folder_sort_item(folder["name"], index_page), key, natural)
        # フォルダの見せかたは、入口ページ（index）の記法で決まる
        # （フォルダ自体は記法を持たないため）。入口が無ければファイル名扱い。
        folder_fmt = _format_for(index_page, fmt_md, fmt_pk) if index_page is not None else "FILE"

        if not inner:
            # 中身が入口ページだけのフォルダ。畳んでも何も出てこないので、
            # 折りたたみにせず1件のページとして並べる。ここに来る時点で
            # index_pageは必ずある（中身も入口も無ければ上でcontinue済み）。
            # ajaxviewが有効なら、普通のページと同じ「その場で開く」ボタンも
            # 付ける（Wiki設計者の報告:「ajaxviewがフォルダのindexだと反応しない」
            # で発見。技術資料参照）。
            entries.append((folder_key,
                            _render_page(index_page, folder_fmt, ajaxview, display_name=folder["name"])))
            continue

        # ここから先は中身がある（<details>に畳む）場合。summary側にも
        # ajaxviewのボタン・受け皿を付ける（技術資料「<summary>側の
        # ajaxview対応」参照。plugin/ls.jsの手当てとセット）。
        if index_page is not None:
            shown = index_page.title or folder["name"] if folder_fmt == "TITLE" else folder["name"]
            link = f'<a href="/{escape(index_page.pagepath)}">{escape(shown)}</a>'
            if folder_fmt == "BOTH" and index_page.title:
                link += f'<span class="ls-title">{escape(index_page.title)}</span>'
            if ajaxview:
                path = escape(index_page.pagepath)
                head = (
                    f'<button type="button" class="ls-open" data-page="{path}" '
                    'aria-expanded="false" aria-label="ここに開く">▸</button>' + link
                )
                view = '<div class="ls-view" hidden></div>'
                folder_cls = "ls-folder ls-openable"
            else:
                head, view, folder_cls = link, "", "ls-folder"
        else:
            head, view, folder_cls = f'<span class="ls-dirname">{escape(folder["name"])}</span>', "", "ls-folder"

        entries.append((folder_key, (
            f'<li class="{folder_cls}"><details open>'
            f'<summary>{head}</summary>'
            f'{view}'
            f'<ul class="ls-list">{"".join(inner)}</ul>'
            "</details></li>"
        )))

    entries.sort(key=lambda e: e[0], reverse=reverse)
    return [html for _, html in entries]


def _read_excludes(value):
    """除外するページ名を読む。(一覧, エラー文言) を返す。

    `plugin/recent.py` の同名関数と同じ考えかた（`;` 区切り・`\\;` エスケープの
    解析は `wikilib.search.split_filters` に任せる薄いラッパ）。"link"宣言の
    対象にしていないのと同じ理由で、ここでも重複を許容している（除外パターンは
    「ページそのものへの参照」ではなく部分一致/ワイルドカードの指定なので、
    リンク元DBに記録する対象ではない）。"""
    if value is None or str(value).strip() == "":
        return [], None
    parts = split_filters(str(value))
    if any(p == "" for p in parts):
        return None, "除外するページ名が空です（; の前後を確かめてください）: {}".format(value)
    return parts, None


def _convert(resolved, body, context):
    if not context.wiki_dir:
        raise PluginArgumentError("ページの置き場所が分かりません。")

    raw_folder = resolved["folder"]
    folder = _resolve_folder(context, raw_folder)
    if folder is None:
        raise PluginArgumentError(f"フォルダの指定が正しくありません: {raw_folder}")

    excludes, err = _read_excludes(resolved["exclude"])
    if err:
        raise PluginArgumentError(err)

    recursive = resolved["recursive"]
    key, reverse = SORTS[resolved["sort"]]
    # 省略（None）は設定（markdown.listname/pukiwiki.listname）から決める
    # （Wiki設計者の指示、2026-09-18）。明示すればそちらを優先する。
    fmt_md = resolved["format_md"]
    if fmt_md is None:
        fmt_md = _default_format(context.config, "markdown")
    fmt_pk = resolved["format_pk"]
    if fmt_pk is None:
        fmt_pk = _default_format(context.config, "pukiwiki")
    ajaxview = resolved["ajaxview"]
    natural = resolved["natural"]

    node = _scan(context, folder, recursive, excludes)
    if node is not None:
        ref = resolve_page_ref(context.wiki_dir, context.page or "")
        node = _drop_self(node, ref.subpath if ref is not None else None)
    if node is None:
        if raw_folder is None:
            # 省略時に自分の下のフォルダが無いのは「単独ページ」。エラーにしない
            return ""
        raise PluginArgumentError(f"フォルダが見つかりません: /{folder}")

    items = _render_tree(node, fmt_md, fmt_pk, key, reverse, ajaxview, natural)
    if not items:
        if raw_folder is None:
            return ""
        return '<div class="ls ls-empty">（このフォルダにページはありません）</div>'

    cls = "ls"
    if recursive:
        cls += " ls-tree"
    if ajaxview:
        cls += " ls-ajax"
    # 読み込み先は自分自身（このプラグインの _action）。base_url を持たせて、
    # 別のWikiを見ているときやサブパス設置でも正しい宛先になるようにする。
    api = escape(f"{context.base_url}/{PLUGIN_URLPATH}/ls")
    return (f'<nav class="{cls}" data-ls-api="{api}">'
            f'<ul class="ls-list">{"".join(items)}</ul></nav>')


def _action(context):
    """`/.plugin/ls?page=<ページパス>` で、そのページの中身をHTML断片で返す。

    ajaxview=true の一覧から呼ばれる。読み込みに答える処理をこのファイルに置くことで、
    一覧の見せかたと中身の出しかたが1つのプラグインの中で完結する。

    本文のレンダリングは閲覧時とまったく同じ経路（同じレンダラ・同じプラグイン）を
    通すので、表示が食い違わない。1行目のタイトルは一覧側に出ているので取り除く。
    読む中身も閲覧時と同じく**公開されたもの**（DB）にする。

    **閲覧の権限が無いページ（`ref.privilege` が `-`）は読み込ませない**（Wiki設計者の
    指示、2026-09-15）。`published_ref` は `-` でも本文を入れて返すので、ここで見ないと
    ページを開けば403になる本文が、このURLからは読めてしまう。在るかどうかより先に
    見る（ページの表示と同じ順）。一覧に出すページ名・タイトルは変えない
    （Wiki設計者の判断、2026-09-15）。"""
    from bottle import request

    from wikilib.plugins import PluginContext, build_markdown_renderer
    from wikilib.render import render_source, rewrite_content_links

    pagepath = (request.query.getunicode("page", "") or "").strip("/")
    if not pagepath or not is_valid_pagepath(pagepath):
        return '<div class="ls-view-error">ページを指定してください。</div>'

    ref = published_ref(context.wiki_dir, pagepath)
    if ref is not None and ref.privilege == PAGE_NONE:
        return '<div class="ls-view-error">このページを閲覧する権限がありません。</div>'
    if ref is None or not ref.exists:
        return '<div class="ls-view-error">このページはまだありません。</div>'

    # 対象ページを指す実行時情報を作る。#contents などページ自身を見るプラグインが
    # 正しく働くよう、ここで page を差し替えておく。
    sub = PluginContext(config=context.config, farm=context.farm, wiki_dir=context.wiki_dir,
                        page=pagepath, base_url=context.base_url)
    md = build_markdown_renderer(context.config, farm_plugin_dir(context.wiki_dir), sub)
    md_conf = (context.config or {}).get("markdown") or {}
    html, _, _ = render_source(md, ref.body, ref.ext,
                               md_conf.get("first_h1_as_title", True), sub)
    # 添付の裸のファイル名は、そのページ自身の添付として解決させる
    html = rewrite_content_links(html, context.base_url, ref.subpath)
    return f'<div class="ls-view-body">{html}</div>'
