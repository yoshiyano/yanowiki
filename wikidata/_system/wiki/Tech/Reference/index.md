# リファレンス

技術的な詳細の一覧です。設計の背景は [設計方針](/Tech/DesignPolicy)、話題ごとの説明は
[テーマの開発方法](/Tech/ThemeGuide)・[プラグインの開発方法](/Tech/dev_plugin)・
[ページのデータベース](/Tech/PageDataBase) にあります。

## 下位のページ

| ページ | 内容 |
|---|---|
| [URLルーティング](/Tech/Reference/Routing) | URLと、それが指すファイル・画面の対応表。リンクの解決（`resolve_link`） |
| [対象ページの特定と index の決まり](/Tech/Reference/Resolve) | URLからページの実体を決める手順、`index` の決まりの置き場所 |
| [DBと平文の読み分け](/Tech/Reference/DataSource) | どこがDBを読み、どこが平文を読むか。保存の後始末 |
| [検索・一覧の画面](/Tech/Reference/Views) | 検索・Wikiの一覧・ページ一覧のTreeView・更新順の一覧 |
| [テーマと編集画面への受け渡し](/Tech/Reference/EditEntry) | テーマに渡すURL・編集の入口・ホットキー・添付の上限 |
| [名前と置き場所を変える](/Tech/Reference/Rename) | 改名・移動と、リンクの書き換えの決まり |
| [設定ファイル](/Tech/Reference/Config) | 設定ファイルの置き場所・読み込む順番・全項目 |

## 版と改訂（バージョン・リビジョン）

画面のフッタに `Powered by wikiSystem` に続けて `Ver.1.0 Rev.215` の形で出る。
値は `wiki.py` の先頭（import より前）が持つ。

| 名前 | 意味 |
|---|---|
| `VERSION` | 版。main で公開するときに上げる |
| `VERSION_DATE` | その版をGitHubの `main` に初めて公開した日。改訂の数えはじめの日（いまの 1.0 は `2026-09-05`） |
| `REVISION` | `VERSION_DATE` の00:00:00から、いまのHEADまでの総コミット数。コミットするたびに1増やす |

```bash
./wiki.py version           # いまの版と、次のコミットで入れるべき改訂を出す
./wiki.py version --next    # 次の改訂だけを出す（216 のように）
```

値の受け渡しは `set_version_label()`（`wikiconfig.py`）を通し、値そのものは `wiki.py` の
1か所だけが持つ。テーマからは `{{ version }}` で使え、見た目は `common.css` の
`.site-version` が決める。

## バックアップ（差分）

保存のたびに `wikidata/<Wiki名>/pageinfo/backup.db` へ unified diff（上書き前 → 上書き後）を
1件ずつ記録する。

| 列 | 内容 |
|---|---|
| `subpath` | ページの実体パス（拡張子抜き。`Tech/My_Page`） |
| `stamp` | 記録した日時（`yymmdd_hhmmss`）。時点を指す名前も兼ねる |
| `diff` | unified diff 本体 |
| `size` | `diff` のバイト数（上限の判断に使う） |

- DBの無いWikiで初めてバックアップに触れたとき、旧形式の `.diff` ファイルを一度だけ取り込む（元は消さない）。
- **差分の基準はページ本文のDB**なので、`pageinfo/wikiall.db` を失うとそれ以前の記録がたどれなくなる。そのため `pageinfo/wikiall.db.zip` へ1日1回控えを取る（`wikilib.dbbackup`。アクセスをきっかけに、控えが前日以前なら別スレッドで取り直す。壊れたDBでは上書きしない）。
- 履歴のDB自身も同じ瞬間に控える（`pageinfo/backup.db.zip`。2つの控えが同じ時点でないと、戻したときに辻褄が合わないため）。
- DBが無いときは控えから戻す（`pagedb.connect`／`backup.connect` が空で作る前に呼ぶ）。控えの中の `snapshot.txt` に、どこまでの記録に対応する控えかが入っている。本文DBを戻したときは控え以後の記録を順に当てて進め（`roll_forward`）、履歴DBを戻したときは控えの時点からいまへの橋渡しを1本足す（`bridge_to_now`）。
- 合計が `BACKUP_TOTAL_BYTES`（50MB、各Wikiごと）に達したら、`BACKUP_PRUNE_TARGET`（0.5）＝上限の半分まで、ページをまたいで古い保存から消す。**記録が `BACKUP_MIN_KEEP`（20）に満たないページは対象外**で、消していくうちに20件を割ったページもそこで外れる。候補が尽きたら打ち切る。
- 新規作成は「空からの差分」、削除は「全文→空」の差分として記録する。削除では下の統合を行わない（作ってすぐ消すと差し引きゼロになるため）。
- 同じ秒に2回保存した場合は、名前が空くまで1秒ずつずらす。
- **直前の差分が `BACKUP_MERGE_SECONDS`（10分）以内なら、1本の差分にまとめ直す。** 日時は最後に保存した時刻。変化が無くなった場合は記録を残さない。
- 末尾に改行の無い行には `\ No newline at end of file` の印を付ける。

## リンク一覧・DBの詳細

`links` の表のスキーマ、書き込まれる契機、`./wiki.py updatepage` による取り込みは
[ページのデータベース](/Tech/PageDataBase) にあります。

## プラグインの記法

| 記法 | 呼ばれる関数 |
|---|---|
| `#name(args)` | `_convert(resolved, body, context)`（`body` は `None`） |
| `#name(args){本文}` | `_convert(...)`（1行の本文） |
| `#name(args){{ … }}` | `_convert(...)`（複数行の本文。`{{{` を含むなら `{{{{` で囲む） |
| `&name(args);` | `_inline(resolved, body, context)`（`body` は `None`） |
| `&name(args){本文};` | `_inline(...)` |
| `/.plugin/<name>` | `_action(context)` |
| `/.plugin/<name>.css` | プラグイン自身が持つCSS（`plugin/<name>.css`）の配信 |

引数はカンマ区切りで、`PLUGIN_INFO["args"]` の宣言に従って名前ごとに束ねられ、`resolved` に
入る（`key=value` でも、位置でも書ける）。カンマや `=` を含む値は `"`/`'` で囲む。ブロック記法は
リスト項目や引用の中でも働く。詳細は [プラグイン仕様](/Tech/dev_plugin/spec) を参照。

## ディレクトリ構成と全体の流れ

[技術ドキュメントの入口](/Tech) を参照してください。
