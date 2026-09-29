# 閲覧者とアクセス権の受け渡し

いまの閲覧者の問い合わせと成り代わり、表示用の読み出しやプラグインへのアクセス権の渡しかたです。

## 閲覧者の問い合わせと成り代わり（`auth.current_uid`・`auth.act_as`）

いまの閲覧者は `auth.current_uid(wiki_dir, farm)` で得ます。成り代わり中ならその相手、そうで
なければ cookie でログインしている人、どちらでもなければ `None`（未ログイン）です。

システムとして動くときは、明示して `$sys` に成り代わります。

    with auth.act_as(auth.SYSTEM_UID):     # "$sys"
        ...                                # この中では current_uid() が "$sys"

- `$sys` の判定器は、規則にかかわらずすべてのページで `W`
- `act_as` は任意のログインIDにも成り代われる。抜けると（例外でも）一つ外側に戻り、入れ子にできる
- **「要求が無いからシステム」とは推し量りません。** 要求の外では cookie が読めず未ログイン扱いに
  なり、画面から呼ばれる取り込み（名前の変更・`#updateDB`）はログイン中の人の権限で動くためです。
  宣言し忘れたときは、読めるページが減る側に倒れます
- 成り代わりは要求・スレッドごとに独立で、新しいスレッドには引き継がれない
- `$sys` はログインIDとして登録できない形（ログインIDは英数字だけ）なので、cookie で名乗っても通らない
- いまはどこでも `act_as` を使っていません。全ページを対象にしたい場面は、`$sys` の判定器
  （`auth.page_privilege(wiki_dir, auth.SYSTEM_UID)`）を直接渡します

## 表示用の読み出しが持つアクセス権（`PageRef.privilege`）

`pagedb.published_ref` は、いまの閲覧者のそのページのアクセス権を `privilege` に入れて返します。
表示する側は判定器を別に作らず、この値で出す・出さないを決めます。

    ref = pagedb.published_ref(wiki_dir, pagepath)
    ref.privilege     # "W" / "R" / "-"（閲覧者は auth.current_uid から取る）

- **`-` でも本文などのデータは入っています**（今後の拡張で要る場面があるため。設計者の指示）。
  `privilege` を見ずに `body` を出すと、読めない人に本文が漏れます
- 公開されていないページも `None` にせず `exists=False` で返す（本文は空）。無いページでも
  その人が読めるか・書けるかを返すためで、ページの表示は、読めない名前なら無いページでも403に
  する（作成を誘っても、作ったあとで本人が開けないため）。`None` はwiki配下から外れるパスだけ
- **ページが在ること自体は隠しません。** 閲覧できないページが在ると知られることは問題ではない、
  というのが設計者の判断です（2026-09-15）
- `resolve_page_ref`（`paths`）が作る `PageRef` の `privilege` は `None`（誰が見ているかを知らない層のため）
- 判定器は `published_ref` を呼ぶたびに作る（1回あたり1ms前後）
- メニュー（`themes.render_menu`）・`#include`・`#ls` の読み込み表示・目次
  （`PluginContext.page_headings`）も `published_ref` を使い、`-` なら本文を出さない

## プラグインでの扱い（`context.privilege`）

プラグインは `context.privilege.check(ページ名)` でアクセス権を聞けます（閲覧者は
`auth.current_uid` から取る）。別のページの本文を読むなら `ref.privilege` を見ます。
書きかたは [context（実行時の情報）](/Tech/dev_plugin/context) にあります。

| 場面 | `-` のとき |
|---|---|
| `#include` | 本文の代わりに「このページを閲覧する権限がありません: ページ名」。見出しも付けず、差し込み件数にも数えない |
| `#ls` の読み込み表示（`/.plugin/ls?page=…`） | 「このページを閲覧する権限がありません。」 |
| 目次（`PluginContext.page_headings`、`#contents`） | 空の一覧 |
| テーマのメニュー | 出さない |
| `#comment`・`#vote`・`#tasklist` の書き込み（`POST /.plugin/…`） | 403で断る（`#tasklist` は `R` でも断る） |
| `#ls`・`#recent`・`#popular`・`#navi` の一覧 | 閲覧できないページは並べない（`pagelist.scandir`・`walk` の既定 `need=PAGE_READ`） |

- `#comment`・`#vote` の書き込みは `-` だけを断り、`R` は通す（プラグインによる書き換えはユーザの編集とは別に数えるため）。
  `#tasklist` は `W` が無ければ断る
- 自分のページの添付を扱うもの（`#img`・`#ref`）や、自分のページの平文の場所だけを見るもの
  （`#viewable_period`・`#updateDB`）は、ページの表示を通ってから動くので判定を足していない
